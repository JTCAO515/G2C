"""One private worker RPC, with a durable UNKNOWN receipt before sending.

Run inside the existing worker via B's fixed launcher. Credentials are read from
0600 files and are never placed in argv, logs or the result receipt. No retries.
"""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import socket
import stat

from runtime_adapter.contract import VERSION as ADAPTER_VERSION,decode,encode,require
from .runtime_private import read_private
from .runtime_rpc import VERSION,MAX_REQUEST,MAX_RESPONSE


SOCKET=Path('/run/g2c-demo/runtime.sock')


def exchange(token_file,method,params_file,output_file):
    token=read_private(token_file,4096).decode('ascii').strip()
    params=decode(read_private(params_file,MAX_REQUEST))
    require(type(params) is dict,'RUNTIME_RPC_PARAMETER_FIELDS')
    require(token and token not in encode(params).decode(),'RUNTIME_CREDENTIAL_IN_DATA')
    request=encode(dict(version=VERSION,token=token,method=method,params=params))
    require(len(request)<=MAX_REQUEST,'RUNTIME_RPC_REQUEST_BOUND')
    output=Path(output_file);parent=output.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.getuid() and stat.S_IMODE(parent.st_mode)==0o700,
        'RUNTIME_PRIVATE_RESULT_DIRECTORY')
    intent=dict(version=VERSION,status='UNKNOWN',method=method,
        request_sha256=sha256(encode(dict(method=method,params=params))).hexdigest(),
        attempt_id=params.get('attempt_id'),reason='RPC_ACK_NOT_OBSERVED_QUERY_ORIGINAL')
    descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as target:
        target.write(encode(intent));target.flush();os.fsync(target.fileno())
    directory=os.open(output.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.fsync(directory)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
            channel.settimeout(200);channel.connect(str(SOCKET));channel.sendall(request+b'\n')
            with channel.makefile('rb') as response:raw=response.readline(MAX_RESPONSE+2)
        require(raw.endswith(b'\n') and len(raw)<=MAX_RESPONSE+1,'RUNTIME_RPC_RESPONSE_BOUND')
        result=decode(raw[:-1])
        require(type(result) is dict and result.get('version') in (VERSION,ADAPTER_VERSION),'RUNTIME_RPC_RESPONSE')
        temporary=output.with_suffix(output.suffix+'.next')
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb') as target:
            target.write(encode(result));target.flush();os.fsync(target.fileno())
        os.replace(temporary,output);os.fsync(directory)
        return result.get('status','READ')
    finally:os.close(directory)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('method',choices=['call','propose','query','c0','original'])
    parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--params-file',type=Path,required=True)
    parser.add_argument('--output-file',type=Path,required=True)
    args=parser.parse_args()
    try:status=exchange(args.token_file,args.method,args.params_file,args.output_file)
    except (OSError,ValueError,TimeoutError):
        print('UNKNOWN runtime RPC; read the retained receipt and query the original attempt')
        raise SystemExit(1) from None
    print('runtime RPC '+status+'; private result written')


if __name__=='__main__':main()
