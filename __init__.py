import socket,sys,json,time,threading
from itertools import zip_longest
server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)

connections={}
transmission_ids=0

def get_id():
    global transmission_ids
    transmission_ids+=1
    return transmission_ids

def package_data(data):
    if type(data)==type(""):
        data=data.encode()
    if len(data)<63527:
        data+=b" "*(63527-len(data))
    return data

def package_event_data(event,data):
    return package_data(json.dumps({"event":event,"data":data}).encode())

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

def data_splitter(data,n):
    resp=list(grouper(data,n))
    out=[]
    for x in resp:
        out.append("".join([y for y in x if y!=None]))
    return out

def keys_exist(data,keys):
    for x in keys:
        if x in data:
            pass
        else:
            return False
    return True

def unpackage_data(data):
    return data.strip(b" ")

def is_json(data):
    try:
        json_data=json.loads(data)
        return type(json_data)==type({}),json_data
    except:
        return False,False

def on_disconnect(addr):
    print('gaya',addr)
    global connections
    del connections[addr]

def pinger():
    while True:
        time.sleep(0.25)
        for x in list(connections.keys()):
            server.sendto(package_event_data("ping",1),x)

def reliable_send(addr,data):
    data=data_splitter(data,62527)
    id=get_id()
    connections[addr]["acks"][id]=[]
    server.sendto(package_event_data('transmission_request',{'packets':len(data),'id':id}),addr)
    start=time.time()
    while True:
        time.sleep(0.01)
        try:
            if -1 in connections[addr]["acks"][id]:
                break
            else:
                server.sendto(package_event_data('transmission_request',{'packets':len(data),'id':id}),addr)
        except:
            return
    print(time.time()-start)
    start=time.time()
    while True:
        time.sleep(0.01)
        to_break=True
        for x in range(len(data)):
            try:
                if x not in connections[addr]["acks"][id]:
                    to_break=False
                    server.sendto(package_event_data('data_transmission',{'id':id,'index':x,'data':data[x]}),addr)
            except:
                return
        if to_break:
            break
    print(time.time()-start)

def writer():
    while True:
        time.sleep(0.01)
        try:
            for x in connections:
                try:
                    addr=x
                    x=connections[x]
                    if x["write"]!=[]:
                        reliable_send(addr,x["write"][0])
                        del connections[addr]["write"][0]
                except:
                    pass
        except:
            continue

def client_thread(addr,client_func):
    print(addr,"aaya")
    client_func(addr)
    global connections
    transfer_mode=False
    current_id=0
    last_id=0
    data_pool=[]
    start=0
    while True:
        iters=0
        while True:
            time.sleep(0.001)
            msg=""
            try:
                if iters>100:
                    raise Exception("Connection timed out")
                elif connections[addr]["read"]==[]:
                    iters+=1
                else:
                    msg=connections[addr]["read"][0]
                    del connections[addr]["read"][0]
                    break
            except:
                on_disconnect(addr)
                return
        event,data=msg["event"],msg["data"]
        if event=="transmission_request" and keys_exist(data,["packets","id"]):
            if transfer_mode==False:
                last_id=current_id
                current_id=data["id"]
                data_pool=[""]*data["packets"]
                transfer_mode=True
                start=time.time()
                server.sendto(package_event_data('ack',{'id':current_id,'index':-1}),addr)
            elif transfer_mode and current_id==data["id"]:
                server.sendto(package_event_data('ack',{'id':current_id,'index':-1}),addr)
        elif transfer_mode and event=="data_transmission" and keys_exist(data,["index","id","data"]):
            if data["id"]==current_id:
                data_pool[data["index"]]=data["data"]
                server.sendto(package_event_data('ack',{'id':current_id,'index':data["index"]}),addr)
                if "" not in data_pool:
                    transfer_mode=False
                    connections[addr]["out"].append("".join(data_pool))
                    print(len("".join(data_pool)))
                    print(time.time()-start)
                    data_pool=[]
            else:
                server.sendto(package_event_data('ack',{'id':current_id,'index':data["index"]}),addr)
        elif event=="ping":
            pass
        elif event=="ack" and keys_exist(data,["id","index"]):
            if data["id"] not in connections[addr]["acks"]:
                connections[addr]["acks"][data["id"]]=[]
            connections[addr]["acks"][data["id"]].append(data["index"])

def node(addr,client_func):
    global connections
    threading.Thread(target=pinger).start()
    threading.Thread(target=writer).start()
    server.bind(addr)
    while True:
        try:
            msg,addr=server.recvfrom(63527)
        except Exception as e:
            continue
        if len(msg)!=63527:
            continue
        msg=unpackage_data(msg)
        msg_dict=is_json(msg)
        if msg==b"connection_request" and addr not in connections:
            connections[addr]={"read":[],"write":[],"acks":{},"out":[]}
            server.sendto(package_data("connection_establish"),addr)
            threading.Thread(target=client_thread,args=(addr,client_func)).start()
        elif msg==b"connection_establish" and addr not in connections:
            connections[addr]={"read":[],"write":[],"acks":{},"out":[]}
            threading.Thread(target=client_thread,args=(addr,client_func)).start()
        elif addr in connections and msg_dict[0]:
            msg_dict=msg_dict[1]
            if keys_exist(msg_dict,["event","data"]):
                connections[addr]["read"].append(msg_dict)
threading.Thread(target=node,args=(("0.0.0.0",int(sys.argv[1])),lambda x:x)).start()
while True:
    raw_msg=input(">> ")
    if raw_msg=="add":
        send_to=("127.0.0.1",int(input("Port : >> ")))
        server.sendto(package_data(b"connection_request"),send_to)
    else:
        reliable_send(("127.0.0.1",int(input("Port : >> "))),eval(raw_msg))