"""Run the computer interface; bind to loopback only and open the default browser."""
import argparse
import json
import os
from pathlib import Path
import socket
import urllib.request
import webbrowser
import uvicorn
from server.desktop.app import create_app


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--models',type=Path,default=Path('models'))
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--sample',type=Path)
    cli.add_argument('--pid-file',type=Path)
    cli.add_argument('--port',type=int,default=8765)
    cli.add_argument('--no-browser',action='store_true')
    args = cli.parse_args()
    url = f'http://127.0.0.1:{args.port}'
    listener = socket.socket()
    try:
        listener.bind(('127.0.0.1',args.port))
    except OSError:
        listener.close()
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url+'/desktop/ping',timeout=2) as response:
                existing=json.load(response)
            if existing.get('application')=='interview-feedback-desktop':
                if not args.no_browser: webbrowser.open(url)
                print('Desktop interface is already running: '+url,flush=True)
                return
        except Exception:
            pass
        raise SystemExit('Port is in use by another application. Choose --port with a free port.')
    if args.pid_file:
        args.pid_file.parent.mkdir(parents=True,exist_ok=True)
        args.pid_file.write_text(str(os.getpid()),'ascii')
    listener.listen(128)
    app = create_app(args.models,args.output,args.sample)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port,log_level='warning',access_log=False,ws='none'))
    print('Desktop interface: '+url,flush=True)
    if not args.no_browser:
        import threading
        def open_ready():
            import time
            for _ in range(100):
                if server.started:
                    webbrowser.open(url)
                    return
                time.sleep(.1)
        threading.Thread(target=open_ready,daemon=True).start()
    try: server.run(sockets=[listener])
    finally:
        listener.close()
        if args.pid_file and args.pid_file.is_file() and args.pid_file.read_text('ascii')==str(os.getpid()):
            args.pid_file.unlink()

if __name__=='__main__':main()
