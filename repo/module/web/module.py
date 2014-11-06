#
# Collective Knowledge (CK web service)
#
# See CK LICENSE.txt for licensing details
# See CK Copyright.txt for copyright details
#
# Developer: Grigori Fursin
#

cfg={}  # Will be updated by CK (meta description of this module)
work={} # Will be updated by CK (temporal data)
ck=None # Will be updated by CK (initialized CK kernel) 

# Local settings
import os
import sys
import cgi
import urllib
import base64
import tempfile

# Import various modules while supporting both Python 2.x and 3.x
try:
   from http.server import BaseHTTPRequestHandler, HTTPServer
except:
   from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

try:
   import urllib.parse as urlparse
except:
   import urlparse

try:
   from urllib.parse import quote as urlquote
except:
   from urllib import quote as urlquote

try:
   from urllib.parse import unquote as urlunquote
except:
   from urllib import unquote as urlunquote

#try:
#   import http.cookies as Cookie
#except:
#   import Cookie

try:
   from socketserver import ThreadingMixIn
except:
   from SocketServer import ThreadingMixIn

##############################################################################
# Initialize module

def init(i):
    """

    Input:  {}

    Output: {
              return       - return code =  0, if successful
                                         >  0, if error
              (error)      - error text if return > 0
            }

    """
    return {'return':0}

##############################################################################
# Access CK through CMD (can detach console)

def call_ck(i):

    """
    Input:  {
              Input for CK
            }

    Output: {
            }
    """

    import tempfile
    import subprocess

    # Check action
    action=i.get('action','')
    if action=='':
       return {'return':1, 'error':'action is not defined'}

    # Generate tmp file
    fd, fn=tempfile.mkstemp(suffix='.tmp', prefix='ck-') # suffix is important - CK will delete such file!
    os.close(fd)

    dc=i.get('detach_console','')
    if dc=='yes': i['out']='con' # Force console if detached

    # Prepare dummy output
    rr={'return':0}
    rr['stdout']=''
    rr['stderr']=''

    # Save json to temporay file
    rx=ck.save_json_to_file({'json_file':fn, 'dict':i})
    if rx['return']>0: return rx

    # Prepare command line
    cmd='ck '+action+' @'+fn
    if dc=='yes':
       # Check platform
       rx=ck.get_platform({})
       if rx['return']>0: return rx

       plat=rx['platform']

       dci=ck.cfg.get('detached_console',{}).get(plat,{})

       dcmd=dci.get('cmd','')
       if dcmd=='':
          return {'return':1, 'error':'detached console is requested but cmd is not defined in kernel configuration'}

       dcmd=dcmd.replace('$#cmd#$', cmd)

       if dci.get('use_create_new_console_flag','')=='yes':
          process=subprocess.Popen(dcmd, stdin=None, stdout=None, stderr=None, shell=True, close_fds=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
       else:
          # Will need to do the forking
          try:
             pid=os.fork()
          except OSError as e:
             return {'return':1, 'error':'forking detached console failed ('+format(e)+')'}

          if pid==0:
             os.setsid()

             pid=os.fork()
             if pid!=0: os._exit(0)

             try:
                 maxfd=os.sysconf("SC_OPEN_MAX")
             except (AttributeError, ValueError):
                 maxfd=1024

             for fd in range(maxfd):
                 try:
                    os.close(fd)
                 except OSError:
                    pass

             os.open('/dev/null', os.O_RDWR)
             os.dup2(0, 1)
             os.dup2(0, 2)

             # Normally child process
             process=os.system(dcmd)
             os._exit(0)

       stdout=ck.cfg.get('detached_console_html','Console was detached ...')
       stderr=''
    else:
       process=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
       stdout,stderr=process.communicate()

#    if stdout!=None: stdout=cm_stdout.decode("utf-8").strip()
#    if stderr!=None: stderr=cm_stderr.decode("utf-8").strip()

    rr['stdout']=stdout
    rr['stderr']=stderr

    return rr

##############################################################################
# Send error to HTTP stream

def web_err(i):

    """
    Input:  {
              http - http object
              type - content type
              bin  - bytes to output
            }

    Output: {
              return - 0
            }
    """

    http=i['http']
    tp=i['type']
    bin=i['bin']

    bin1=bin+b'! Please, report to developers '+ck.cfg['ck_web'].encode('utf-8')

    if tp=='json':
       bin2=b'{"return":1, "error":"'+bin1+b'"}'
    else:
       bin2=b'<html><bin>'+bin1+b'</html></body>'

    i['bin']=bin2
    return web_out(i)

##############################################################################
# Send error to HTTP stream

def web_out(i):

    """

    Input:  {
              http - http object
              type - content type
              bin  - bytes to output
            }

    Output: { 
              return - 0
            }
    """
    
    http=i['http']
    tp=i['type']
    bin=i['bin']

    tpx=cfg['content_types'].get(tp,'')
    if tpx=='': 
       tp='web'
       tpx=cfg['content_types'][tp]

    # Output
    http.send_header('Content-type', tpx+';charset=utf-8')
    http.send_header('Content-Length', str(len(bin)))
    http.end_headers()
    http.wfile.write(bin)

    return {'return':0}

##############################################################################
# Process CK web service request (both GET and POST)

def process_ck_web_request(i):

    """

    Input:  {
              http - Python http object
            }

    Output: { None }
    """

    # http object
    http=i['http']

    # Parse GET variables and path
    xget={}
    xpath={'first':'', 'rest':'', 'query':''}

    xt='json' # Return RAW run, return json

    # Check GET variables
    if http.path!='':
       http.send_response(200)

       a=urlparse.urlparse(http.path)
       xp=a.path
       xr=''

       if xp.startswith('/'): xp=xp[1:]

       u=xp.find('/')
       if u>=0:
          xr=xp[u+1:]
          xp=xp[:u]

       xpath['first']=xp
       xpath['rest']=xr
       xpath['query']=a.query
       b=urlparse.parse_qs(a.query, keep_blank_values=True, )

       if xp!='':
          xt=xp

       xget={}
       for k in b:
#           xget[k]=b[k][0]
            xget[k]=urlunquote(b[k][0])
            if sys.version_info[0]<3:
               xget[k]=xget[k].decode('utf8')

    # Check POST
    xpost={}
    xpost1={}

    try:
       headers = http.headers
       content_type = headers.get('content-type')
       ctype=''
       if content_type != None:
          ctype, pdict = cgi.parse_header(content_type)
          # Python3 cgi.parse_multipart expects boundary to be bytes, not str.
          if sys.version_info[0]<3 and 'boundary' in pdict: 
             pdict['boundary'] = pdict['boundary'].encode()

       if ctype == 'multipart/form-data':
          if sys.version_info[0]<3:
             xpost1 = cgi.parse_multipart(http.rfile, pdict)
          else:
             xxpost1 = cgi.FieldStorage(fp=http.rfile, headers=headers, environ={'REQUEST_METHOD':'POST'})
             for k in xxpost1.keys():
                 xpost1[k]=[xxpost1[k].value]
       elif ctype == 'application/x-www-form-urlencoded':
          length = int(http.headers.get('content-length'))
          s=http.rfile.read(length)
          if sys.version_info[0]>2: s=s.decode('utf8')
          xpost1 = cgi.parse_qs(s, keep_blank_values=1)

    except Exception as e:
       bin=b'internal CK web service error [7101] ('+format(e).encode('utf8')+')'
       web_err({'http':http, 'type':xt, 'bin':bin})
       ck.out(ck.cfg['error']+bin.decode('utf8'))
       return

    # Post processing
    for k in xpost1:
        v=xpost1[k]
        if k.endswith('[]'): 
           k1=k[:-2]
           xpost[k1]=[]
           for l in v:
               xpost[k1].append(urlunquote(l))
        else: 
           xpost[k]=urlunquote(v[0])

        if sys.version_info[0]<3:
           xpost[k]=xpost[k].decode('utf8')

    # Prepare input and check if CK json present
    ii=xget

    cj=xpost.get('ck_json','').strip()
    if cj!='':
       r=ck.convert_json_str_to_dict({'str':cj, 'skip_quote_replacement':'yes'})
       if r['return']>0: 
          bin=b'internal CK web service error [7102] ('+r['error'].encode('utf8')+b')'
          web_err({'http':http, 'type':xt, 'bin':bin})
          ck.out(ck.cfg['error']+bin.decode('utf8'))
          return

       ii.update(r['dict'])
    else:
       ii.update(xpost)

    # Check how to run #################
    if xt=='json':
       ######################### JSON ##################################################
       # Prepare temporary output file
       fd, fn=tempfile.mkstemp(prefix='ck-')
       os.close(fd)

       # Call CK
       ii['out']='json_file'
       ii['out_file']=fn

       bin=b''

       r=call_ck(ii)

       if r['return']==0:
          # Load output json file
          r=ck.load_text_file({'text_file':fn, 'keep_as_bin':'yes'})
          if r['return']==0:
             bin=r['bin']

       if r['return']>0:
          rx=ck.dumps_json({'dict':r})
          if rx['return']>0:
             bin=b'{"return":1, "error": "internal CK web service error [7102] ('+rx['error'].encode('utf8')+b')"}' 
          else:
             bin=rx['string'].encode('utf-8')

       # Remove temporary file
       if os.path.isfile(fn): os.remove(fn)

       # Output
       web_out({'http':http, 
                'type':xt, 
                'bin':bin})
       
    elif xt=='web':
       ######################### HTML ##################################################
       web_out({'http':http, 
                'type':xt, 
                'bin':'<html><body>To be implemented!</body></html>'})





    else:
       web_out({'http':http, 
                'type':'web', 
                'bin':'<html><body>Unknown CK request!</body></html>'})

    return

##############################################################################
# Class to handle requests in separate threads

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):

    """
    """

##############################################################################
# Class to handle CK web service requests

class server_handler(BaseHTTPRequestHandler):

    """
    Input:  Python http handler
    Output: None
    """

    # Process only GET
    def do_GET(self):
        process_ck_web_request({'http':self})
        return
     
    # Process GET and POST
    def do_POST(self):
        process_ck_web_request({'http':self})
        return

    def log_request(self, code='-', size='-'):
        self.log_message('"%s" %s %s', self.requestline, str(code), str(size))
        return

    def log_error(self, format, *args):
        self.log_message(format, *args)
        return

##############################################################################
# start web service

def start(i):
    """

    Input:  {
              (host)       - Web host
              (port)       - Web port
            }

    Output: {
              return       - return code =  0, if successful
                                         >  0, if error
              (error)      - error text if return > 0
            }

    """

    ck.out('For now we can only start server indefinitely')
    ck.out("but we should add a proper start/stop/resume support at some point ...")

    # Prepare host (if '' - localhost)
    host=ck.cfg.get('default_web_service_host','')
    if i.get('host','')!='': host=i['host']

    xhost='localhost'
    if host!='': xhost=host

    port=ck.cfg.get('default_web_service_port','')
    if i.get('port','')!='': port=i['port']

    if port=='':
       return {'return':1, 'error':'web port is not defined'}

    ck.out('')
    ck.out('Starting CK web service on '+xhost+':'+port+' ...')
    ck.out('')

    sys.stdout.flush()

    try:
       server = ThreadedHTTPServer((host, int(port)), server_handler)
       # Prevent issues with socket reuse
       server.allow_reuse_address=True
       server.serve_forever()
    except KeyboardInterrupt:
       ck.out('Keyboard interrupt, terminating CK web service ...')
       server.socket.close()
       return {'return':0}
    except OSError as e:
       return {'return':1, 'error':'problem starting CK web service ('+format(e)+')'}

    return {'return':0}