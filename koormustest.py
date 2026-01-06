import argparse
import threading
import time
import random
import requests
import ast
from queue import Queue

# -------------------------------
# CLI
# -------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-u", required=True, help="Serveri base URL")
    p.add_argument("-c", type=int, required=True, help="Kasutajate arv")
    p.add_argument("-n", type=int, required=True, help="Päringuid sekundis kokku")
    p.add_argument("-t", type=int, required=True, help="Testi kestus sekundites")
    p.add_argument("-k", action="store_true", help="Ignoreeri SSL vigu")
    return p.parse_args()


# -------------------------------
# Rate limiter (globaalne)
# -------------------------------

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


# -------------------------------
# Requestide laadimine
# -------------------------------

def load_requests(filename="request.txt"):
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
            parts2=parts[2].split('} ', maxsplit=1)

            headers = ast.literal_eval(parts2[0]) if len(parts2) > 0 else {}
            body = parts2[1] if len(parts2) > 1 else None

            reqs.append((method, path, headers, body))
    return reqs


# -------------------------------
# Kasutaja tööloogika
# -------------------------------

def user_worker(
    user_id,
    base_url,
    requests_data,
    rate_limiter,
    stop_time,
    verify_ssl,
):
    session = requests.Session()
    session.verify = verify_ssl

    try:
        session.post(f"{base_url}/rkvr/auth/devlogin/login",     data={"48806260018"},
        )

        while time.time() < stop_time:
            method, path, headers, body = random.choice(requests_data)
            url = base_url + path

            rate_limiter.wait()

            try:
                if method == "GET":
                    r = session.get(url, headers=headers)
                else:
                    r = session.post(url, headers=headers, data=body)

                print(user_id, method, path, r.status_code)

            except Exception as e:
                print(f"[User {user_id}] request error: {e}")

    finally:
        session.close()


# -------------------------------
# Main
# -------------------------------

def main():
    args = parse_args()

    requests_data = load_requests()
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
                requests_data,
                rate_limiter,
                stop_time,
                not args.k,
            ),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
