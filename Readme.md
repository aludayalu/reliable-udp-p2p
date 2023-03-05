# Reliable UDP P2P In Python
## Basic Usage
Echo Server
```python
from node import *
def client_thread(conn):
    print("Client with id",conn.id,"has connected")
    while True:
        conn.send(conn.recv())
node(("127.0.0.1",1),client_thread)
```
Client
```python
from node import *
def client_thread(conn):
    print("Client with id",conn.id,"has connected")
    while True:
        print(conn.recv())
node(("0.0.0.0",7777),client_thread)
conn=connection(("127.0.0.1",1))
def sender():
    while True:
        conn.send(input(">> "))
thread(target=sender).start()
```