import asyncore
import sys
import shlex
import json
from time import time
from os import stat, listdir
from os.path import isfile, isdir
from os.path import exists as path_exists
from os.path import join as path_join
from mimetypes import types_map
from .common import *
from .common import __version__ as VERSION

types_map[".manifest"] = "text/cache-manifest"
types_map[".ico"] = "image/x-icon"
types_map[".json"] = "application/json"
types_map[".xml"] = "application/xhtml+xml"


class HTTPConnection(asyncore.dispatcher):
    """To provide a simple HTTP response handler.
    Special methods can be implementd by subclassing this class
    """

    def __init__(self, conn, addr, context):
        asyncore.dispatcher.__init__(self, sock=conn)
        self.addr = addr
        self.context = context
        self.in_buffer = b""
        self.out_buffer = b""
        self.content_length = 0
        self.check_input = self.read_headers
        self.query = ''
        self.raw_post_data = ""
        # Timeout acts also as flag to signal
        # a connection which still waits for a response
        self.timeout = 0
        self.cgi_enabled = context.cgi_enabled
        self.cgi_script = ""
        self.GET_handlers = context.http_get_handlers

    def read_headers(self):
        raw_parsed_headers = parse_headers(self.in_buffer)
        if raw_parsed_headers:
            # to dispatch any hanging timeout response
            self.flush()
            (headers_raw, first_line,
             self.headers, self.in_buffer) = raw_parsed_headers
            method, path, protocol = first_line.split(BLANK, 2)
            # if path == "/app/":
            #    path = "/app/stp-1/client-en.xml"
            self.REQUEST_URI = path
            path = path.lstrip(b"/")
            if b"?" in path:
                path, self.query = path.split(b'?', 1)
            arguments = path.split(b"/")
            command = (arguments and arguments.pop(0) or b"").decode()
            command = command.replace('-', '_').replace('.', '_')
            system_path = URI_to_system_path(path.rstrip(b"/")) or "."
            print('system path', system_path)
            self.method = method
            self.path = path
            self.command = command
            self.arguments = arguments
            self.system_path = system_path
            self.timeout = time() + TIMEOUT
            # if not self.REQUEST_URI.endswith("services"):
            #    print self.REQUEST_URI
            if self.cgi_enabled:
                self.check_is_cgi(system_path)
            # POST
            if method == "POST":
                if "Content-Length" in self.headers:
                    self.content_length = int(self.headers["Content-Length"])
                    self.check_input = self.read_content
                    self.check_input()
            # GET
            elif method == b"GET":
                if hasattr(self, command) and \
                        hasattr(getattr(self, command), '__call__'):
                    getattr(self, command)()
                elif command in self.GET_handlers:
                    self.out_buffer += self.GET_handlers[command](self.headers)
                    self.timeout = 0
                else:
                    if self.cgi_script:
                        self.handle_cgi()
                    elif os.path.exists(system_path) or not path:
                        self.serve(path, system_path)
                    # favicon.ico and device-favicon.png
                    elif path_exists(path_join(SOURCE_ROOT, system_path)):
                        self.serve(path, path_join(SOURCE_ROOT, system_path))
                    else:
                        content = "The server cannot handle: %s" % path
                        self.out_buffer += NOT_FOUND % (
                            get_timestamp(),
                            len(content),
                            content)
                        self.timeout = 0
                if self.in_buffer:
                    self.check_input()
            # Not implemented method
            else:
                content = b"The server cannot handle: %s" % method
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    str.encode(str(len(content))),
                    content)
                self.timeout = 0

    def check_is_cgi(self, system_path, handler=".cgi"):
        # system path of the cgi script
        self.cgi_script = ""
        self.SCRIPT_NAME = ""
        self.PATH_INFO = ""
        if handler in system_path:
            script_path = system_path[0:system_path.find(
                handler) + len(handler)]
            if isfile(script_path):
                self.cgi_script = script_path
                pos = self.REQUEST_URI.find(handler) + len(handler)
                self.SCRIPT_NAME = self.REQUEST_URI[0:pos]
                path_info = self.REQUEST_URI[pos:]
                if "?" in path_info:
                    path_info = path_info[0:path_info.find("?")]
                self.PATH_INFO = path_info
        return bool(self.cgi_script)

    def handle_cgi(self):
        import subprocess
        is_failed = False
        remote_addr, remote_port = self.socket.getpeername()
        cwd = os.getcwd()
        environ = {
            # os
            "COMSPEC": os.environ.get("COMSPEC", ""),
            "PATH": os.environ["PATH"],
            "PATHEXT": os.environ.get("PATHEXT", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
            # server
            "DOCUMENT_ROOT": os.getcwd().replace(os.path.sep, "/"),
            "GATEWAY_INTERFACE": "CGI/1.1",
            "QUERY_STRING": self.query,
            "REMOTE_ADDR": remote_addr,
            "REMOTE_PORT": str(remote_port),
            "REQUEST_METHOD": self.method,
            "REQUEST_URI": self.REQUEST_URI,
            "SCRIPT_FILENAME": cwd.replace(os.path.sep, "/") + self.SCRIPT_NAME,
            "SCRIPT_NAME": self.SCRIPT_NAME,
            "SERVER_ADDR": self.context.SERVER_ADDR,
            "SERVER_ADMIN": "",
            "SERVER_NAME": self.context.SERVER_NAME,
            "SERVER_PORT": str(self.context.SERVER_PORT),
            "SERVER_PROTOCOL": " HTTP/1.1",
            "SERVER_SIGNATURE": "",
            "SERVER_SOFTWARE": "dragonkeeper/%s" % VERSION,
        }
        if self.PATH_INFO:
            environ["PATH_INFO"] = self.PATH_INFO
            environ["PATH_TRANSLATED"] = \
                cwd + self.PATH_INFO.replace("/", os.path.sep)
        if "Content-Length" in self.headers:
            environ["CONTENT_LENGTH"] = self.headers["Content-Length"]
        if "Content-Type" in self.headers:
            environ["CONTENT_TYPE"] = self.headers["Content-Type"]
        for header in self.headers:
            key = "HTTP_%s" % header.upper().replace('-', '_')
            environ[key] = self.headers[header]
        script_abs_path = os.path.abspath(self.cgi_script)
        response_code = 200
        response_token = 'OK'
        stdoutdata = ""
        stderrdata = ""
        headers = {}
        content = ""
        try:
            file = open(script_abs_path, 'rb')
            first_line = file.readline()
            file.close()
        except:
            is_failed = True
        if not is_failed:
            if first_line.startswith("#!"):
                first_line = first_line[2:].strip()
            else:
                is_failed = True
        if not is_failed:
            command = shlex.split(first_line)
            command.append(script_abs_path)
            p = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environ,
                cwd=os.path.split(script_abs_path)[0]
            )
            input = None
            if self.method == "POST":
                input = self.raw_post_data
            stdoutdata, stderrdata = p.communicate(input)
            if stderrdata:
                content = "\n". join([
                    "Error occured in the subprocess",
                    "-------------------------------",
                    "",
                    stderrdata
                ])
                headers['Content-Type'] = 'text/plain'
            elif stdoutdata:
                raw_parsed_headers = parse_headers(CRLF + stdoutdata)
                if raw_parsed_headers:
                    (headers_raw, first_line,
                     headers, content) = raw_parsed_headers
                    if 'Status' in headers:
                        response_code, response_token = \
                            headers.pop('Status').split(' ', 1)
                else:
                    # assume its html
                    content = stdoutdata
                    headers['Content-Type'] = 'text/html'

        headers['Content-Length'] = len(content)
        self.out_buffer += RESPONSE_BASIC % (
            response_code,
            response_token,
            get_timestamp(),
            "".join(
                ["%s: %s\r\n" % (key, headers[key]) for key in headers] +
                [CRLF, content]
            )
        )
        self.timeout = 0

    def read_content(self):
        if len(self.in_buffer) >= self.content_length:
            self.raw_post_data = self.in_buffer[0:self.content_length]
            if self.cgi_script:
                self.handle_cgi()
            elif hasattr(self, self.command):
                getattr(self, self.command)()
            else:
                content = "The server cannot handle: %s" % self.path
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
            self.raw_post_data = ""
            self.in_buffer = self.in_buffer[self.content_length:]
            self.content_length = 0
            self.check_input = self.read_headers
            if self.in_buffer:
                self.check_input()

    def serve(self, path, system_path):
        if path_exists(system_path) or path == b"":
            if isfile(system_path):
                self.serve_file(path, system_path)
            elif isdir(system_path) or path == b"":
                self.serve_dir(path, system_path)
        else:
            content = "The sever couldn't find %s" % system_path
            self.out_buffer += NOT_FOUND % (
                get_timestamp(),
                len(content),
                content)
            self.timeout = 0

    def serve_file(self, path, system_path):
        if b"If-Modified-Since" in self.headers and \
           timestamp_to_time(self.headers[b"If-Modified-Since"]) >= \
           int(stat(system_path).st_mtime):
            self.out_buffer += NOT_MODIFIED % get_timestamp()
            self.timeout = 0
        else:
            print('path', path)
            ending = (b"." in path and path[path.rfind(
                b"."):] or b"no-ending").decode()
            mime = str.encode(
                ending in types_map and types_map[ending] or 'text/plain')
            try:
                response_template = RESPONSE_OK_CONTENT
                if isfile(system_path + '.gz'):
                    response_template = RESPONSE_OK_CONTENT_GZIP
                    system_path += '.gz'
                f = open(system_path, 'rb')
                content = f.read()
                f.close()
                self.out_buffer += response_template % (
                    get_timestamp(),
                    b'Last-Modified: %s%s' % (
                        get_timestamp(system_path),
                        CRLF),
                    mime,
                    str.encode(str(len(content))),
                    content)
                self.timeout = 0
            except:
                content = "The server cannot find %s" % system_path
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
                self.timeout = 0

    def serve_dir(self, path, system_path):
        if path and not path.endswith(b'/'):
            self.out_buffer += REDIRECT % (get_timestamp(), path + b'/')
            self.timeout = 0
        else:
            print('system_path', system_path)
            try:
                items_dir = [item for item in listdir(system_path)
                             if isdir(path_join(system_path, item))]
                items_file = [item for item in listdir(system_path)
                              if isfile(path_join(system_path, item))]
                items_dir.sort()
                items_file.sort()
                if path:
                    items_dir.insert(0, '..')
                print('>>> 0', items_dir)
                markup = [ITEM_DIR % (str.encode(quote(item)), str.encode(item))
                          for item in items_dir]
                print('>>> 1')
                markup.extend([ITEM_FILE % (str.encode(quote(item)), str.encode(item))
                               for item in items_file])
                print('>>> 2')
                content = DIR_VIEW % (b"".join(markup))
            except Exception as msg:
                print('msg >>>', msg)
                print("OS error: {0}".format(msg))
                content = DIR_VIEW % str.encode(
                    """<li style="color:#f30">%s</li>""" % (msg))
            self.out_buffer += RESPONSE_OK_CONTENT % (
                get_timestamp(),
                b'',
                b"text/html",
                str.encode(str(len(content))),
                content)
            self.timeout = 0

    def proxy(self):
        import urllib
        try:
            response = urllib.urlopen(self.raw_post_data)
            content = response.read()
            self.out_buffer += RESPONSE_OK_CONTENT % (
                get_timestamp(),
                '',
                "text/html",
                len(content),
                content)
        except:
            content = "The server cannot handle: %s" % method
            self.out_buffer += NOT_FOUND % (
                get_timestamp(),
                len(content),
                content)
            self.timeout = 0
        self.timeout = 0

    def base64_2png(self):
        import json
        import upnpsimpledevice
        resp_msg = None
        try:
            """
            message format
            {
                directory: <relative URL>,
                data: <base64 string>
            }
            """
            msg = json.loads(self.raw_post_data)
            file_name = "%s.png" % upnpsimpledevice.get_uuid()
            sys_path = URI_to_system_path(msg.get("directory"))
            if not path_exists(sys_path):
                os.mkdir(sys_path)
            path = path_join(sys_path, file_name)
            fh = open(path, "wb")
            fh.write(msg.get("data").decode('base64'))
            fh.close()
            resp_msg = {
                "status": "OK",
                "file_name": file_name
            }
        except:
            resp_msg = {
                "status": "Error"
            }
        content = json.dumps(resp_msg)
        self.out_buffer += RESPONSE_OK_CONTENT % (
            get_timestamp(),
            "",
            "text/plain",
            len(content),
            content)
        self.timeout = 0

    # ============================================================
    #
    # ============================================================
    def flush(self):
        pass
    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================

    def handle_read(self):
        b = self.recv(BUFFERSIZE)
        print('read', b[0:20])
        self.in_buffer += b
        self.check_input()

    def writable(self):
        return bool(self.out_buffer)

    def handle_write(self):
        print('write', self.out_buffer[0:20])
        sent = self.send(self.out_buffer)
        self.out_buffer = self.out_buffer[sent:]

    def handle_close(self):
        self.close()
