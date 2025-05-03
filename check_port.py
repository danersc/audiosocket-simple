import socket

def check_port(port):
    s = socket.socket()
    try:
        s.bind(('0.0.0.0', port))
        print(f'Porta {port} está livre')
        s.close()
        return True
    except:
        print(f'Porta {port} está em uso')
        return False

if __name__ == "__main__":
    check_port(8080)