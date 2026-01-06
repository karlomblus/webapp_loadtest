import argparse
import threading
import time
import random
import requests
import ast
from queue import Queue
import warnings

start_time = time.time()
stats_lock = threading.Lock()
total_requests = 0
total_duration = 0.0  # sekundites

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-u", required=True, help="Serveri base URL")
    p.add_argument("-c", type=int, required=True, help="Kasutajate arv")
    p.add_argument("-n", type=int, required=True, help="Päringuid sekundis kokku")
    p.add_argument("-t", type=int, required=True, help="Testi kestus sekundites")
    p.add_argument("-k", action="store_true", help="Ignoreeri SSL vigu")
    return p.parse_args()


class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            delta = now - self.last
            if delta < self.interval:
                time.sleep(self.interval - delta)
            self.last = time.time()


def load_requests(filename):
    reqs = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(maxsplit=2) # jagame kolmeks jupiks  METHOD, PATH, ÜLEJÄÄNUD
            method = parts[0].upper()
            path = parts[1]
            # kuna header on ainult ühekihiline json, siis post data splitime selle järgi
            parts2=parts[2].split('}', maxsplit=1)
            headers = ast.literal_eval(parts2[0]+'}') if len(parts2) > 0 else {}
            body = parts2[1][1:] if len(parts2) > 1 else None
            #print("Parsime requesti: ",method," ",path,"\nHeader:",headers,"\n'",body,"'\n\n")
            reqs.append((method, path, headers, body))
    return reqs

def work_time():
    global start_time
    elapsed_time = time.time() - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{int(hours):02}:{int(minutes):02}:{int(seconds):02}'




def user_worker(    user_id,    base_url,  startup_requests_data,  requests_data,    rate_limiter,    stop_time,    verify_ssl,):
    session = requests.Session()
    session.verify = verify_ssl
    global total_requests,total_duration
    if not session.verify: # kui oleme kontrolli välja lülitanud, ei taha hoiatusi ka
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    

    try:
        #TODO: startup

        while time.time() < stop_time:
            method, path, headers, body = random.choice(requests_data)
            url = base_url + path

            rate_limiter.wait()
            

            try:
                start = time.perf_counter()
                if method == "GET":
                    r = session.get(url, headers=headers)
                else:
                    r = session.post(url, headers=headers, data=body)
                duration = time.perf_counter() - start
                print(work_time(),user_id, method, path, r.status_code)

                with stats_lock:
                    total_requests += 1
                    total_duration += duration
                
                if r.status_code!=200:
                    print("VIGA!!")
                    print("Request: ",method," ",path,"\nHeader:",headers,"\n"+body+"\n"+ r.text+"\n")

            except Exception as e:
                print(f"[User {user_id}] request error: {e}")

    finally:
        session.close()

def stats_printer(stop_time):
    global start_time
    while time.time() < stop_time:
        time.sleep(10)

        with stats_lock:
            if total_requests == 0:
                continue
            avg = total_duration / total_requests
            elapsed_time = time.time() - start_time
            avg2=  total_requests/elapsed_time

        print(
            f"[STATS] requests={total_requests}, "
            f"avg_duration_ms={avg*1000:.2f}, total avg={avg2:.1f} req/s"
        )



def main():
    args = parse_args()

    startup_requests_data = load_requests("startup_requests.txt")
    if not startup_requests_data:
        raise RuntimeError("startup_requests.txt on tühi")
    requests_data = load_requests("request.txt")
    if not requests_data:
        raise RuntimeError("request.txt on tühi")


    rate_limiter = RateLimiter(args.n)
    stop_time = time.time() + args.t
    

    threads = []

    for i in range(args.c):
        t = threading.Thread(
            target=user_worker,
            args=(
                i,
                args.u.rstrip("/"),
                startup_requests_data,
                requests_data,
                rate_limiter,
                stop_time,
                not args.k,
            ),
            daemon=True,
        )
        t.start()
        threads.append(t)

    stats_thread = threading.Thread(     target=stats_printer,      args=(stop_time,),     daemon=True,)
    stats_thread.start()


    for t in threads:
        t.join()



    with stats_lock:
        avg = (total_duration / total_requests) if total_requests else 0
        elapsed_time = time.time() - start_time # kogu programmi tööaeg
        avg2= total_requests/elapsed_time
        print(    f"\n[FINAL STATS] requests={total_requests}, avg_duration_ms={avg*1000:.2f}, total avg={avg2:.1f} req/s")

if __name__ == "__main__":
    main()
