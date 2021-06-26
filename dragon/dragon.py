from dragon.httpconnection import HTTPConnection
import sys
import os
import socket
import argparse
import asyncore
from .simpleserver import SimpleServer


if sys.platform == "win32":
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)


def _get_IP():
    ip = None
    hostname, aliaslist, ips = socket.gethostbyname_ex(socket.gethostname())
    while ips and ips[0].startswith("127."):
        ips.pop(0)
    if len(ips) == 1:
        ip = ips[0]
    else:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("opera.com", 80))
            ip = s.getsockname()[0]
            s.close()
        except:
            pass
    return ip


def _parse_args():
    parser = argparse.ArgumentParser(description="""
                                     Developper tool for Opera Dragonfly.
                                     Translates STP to HTTP.
                                     Exit: Control-C""")
    parser.add_argument("-r", "--root",
                        default=".",
                        help="the root directory of the server (default: %(default)s))")
    parser.add_argument("-s", "--server-port",
                        type=int,
                        default=8002,
                        dest="SERVER_PORT",
                        help="server port (default: %(default)s))")
    parser.add_argument("--host",
                        default="0.0.0.0",
                        dest="host",
                        help="host (default: %(default)s))")
    parser.add_argument("-v", "--verbose",
                        action="store_true",
                        default=False,
                        dest="verbose_debug",
                        help="print verbose debug info")
    parser.add_argument("--cgi",
                        action="store_true",
                        default=False,
                        dest="cgi_enabled",
                        help="enable cgi support")
    parser.add_argument("--servername",
                        default="localhost",
                        dest="SERVER_NAME",
                        help="server name (default: %(default)s))")
    parser.add_argument("--timeout",
                        type=float,
                        default=0.1,
                        dest="poll_timeout",
                        help="timeout for asyncore.poll (default: %(default)s))")
    parser.set_defaults(ip=_get_IP(), http_get_handlers={})
    return (parser, parser.parse_args())


def _run_proxy(args, count=None):
    SimpleServer(args.host, args.SERVER_PORT,
                 HTTPConnection, args)
    print("server on: http://%s:%s/" % (args.SERVER_NAME, args.SERVER_PORT))
    asyncore.loop(timeout=args.poll_timeout, count=count)


def main_func():
    parser, args = _parse_args()
    if not args.ip:
        print("failed to get the IP of the machine")
        return
    if not os.path.isdir(args.root):
        parser.error("""Root directory "%s" does not exist""" % args.root)
        return

    os.chdir(args.root)
    try:
        _run_proxy(args)
    except KeyboardInterrupt:
        asyncore.loop(timeout=args.poll_timeout, count=6)
        try:
            for fd, obj in asyncore.socket_map.items():
                obj.close()
        except:
            # not sure
            pass
        sys.exit()


if __name__ == "__main__":
    main_func()
