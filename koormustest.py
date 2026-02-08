import argparse
import ast
import random
import threading
import time
import warnings
import sys

# from queue import Queue
import requests

start_time = time.monotonic()
stats_lock = threading.Lock()
total_requests = 0
total_duration = 0.0  # sekundites
min_duration = float('inf')
max_duration = 0.0
status_counts = {}    # kõigi staatuskoodide hulk eraldi

def parse_args():
    usage = "python koormustest.py -u URL -c THREAD_COUNT -n TOTAL_RATE -t SECONDS [-f requests.txt] [-k]"
    sample = "Näide: python koormustest.py -u https://example.com -c 20 -n 10 -t 30"
    p = argparse.ArgumentParser(add_help=False, usage=usage, epilog=sample)
    p.add_argument(
        "-h",
        action="store_true",
        help="Näita kõikide võtmete kirjeldusi ja lõpeta programm",
    )
    p.add_argument("-u", required=True, help="Serveri base URL")
    p.add_argument("-c", type=int, required=True, help="Kasutajate arv")
    p.add_argument("-n", type=int, required=True, help="Päringuid sekundis kokku")
    p.add_argument("-t", type=int, required=True, help="Testi kestus sekundites")
    p.add_argument("-f", default="requests.txt", help='Päringute faili nimi (vaikimisi "requests.txt")')
    p.add_argument("-s", default="startup_requests.txt", help='Startup päringute faili nimi (vaikimisi "startup_requests.txt")')
    p.add_argument("--timeout", type=float, default=30.0, help="Päringu timeout sekundites (vaikimisi 30.0)")
    p.add_argument("-k", action="store_true", help="Ignoreeri SSL vigu")
    args = p.parse_args()
    if args.h:
        p.print_help()
        sys.exit(0)
    if args.c < 1:
        p.error("-c peab olema >= 1")
    if args.n < 1:
        p.error("-n peab olema >= 1")
    if args.t < 1:
        p.error("-t peab olema >= 1")
    if args.timeout <= 0:
        p.error("--timeout peab olema > 0")
    return args


class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        # self.last = time.time()
        self.next_time = time.monotonic()  # järgmise lubatud päringu aeg

    def wait(self, stop_time, debugdata):
        # print(debugdata,f"ratelimiter alustab runtime_left={stop_time-time.time()}")
        now = time.monotonic()
        timeout = max(0, stop_time - now)
        #print("lukustamise timeout:", timeout)
        acquired = self.lock.acquire(timeout=timeout)
        if not acquired:
            # print(debugdata,f"ratelimiter loobub luku ootamisest runtime_left={stop_time-time.time()}")
            return False  # ei saanud lukku, aeg läbi
        sleep_time = 0
        try:
            # print(debugdata,f"ratelimiter sai luku runtime_left={stop_time-time.time()}")
            if stop_time < time.monotonic():
                # print(debugdata,f"ratelimiter loobub runtime_left={stop_time-time.time()}")
                return False
            now = time.monotonic()
            # kui järgmine slot on juba möödas, tee kohe
            if now >= self.next_time:
                self.next_time = now + self.interval
                # print(debugdata,f"ratelimiter: tee kohe runtime_left={stop_time-time.time()}")
                return True

            # kui järgmine slot on tulevikus
            sleep_time = self.next_time - now

            # print(debugdata,f"ratelimite: sleebin {sleep_time} runtime_left={stop_time-time.time()}")
            time.sleep(sleep_time)
            self.next_time += self.interval
            return True
        except OverflowError as e:
            print(
                f"[RateLimiter] OverflowError during time.sleep sleep_time={sleep_time}: {e}"
            )
        finally:
            self.lock.release()


def load_requests(filename):
    reqs = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            #print("Parsime requesti rida: ", line)
            parts = line.split(
                maxsplit=2
            )  # jagame kolmeks jupiks  METHOD, PATH, ÜLEJÄÄNUD
            method = parts[0].upper()
            path = parts[1]
            # kuna header on ainult ühekihiline json, siis post data splitime selle järgi
            parts2 = parts[2].split("}", maxsplit=1)
            headers = ast.literal_eval(parts2[0] + "}") if len(parts2) > 0 else {}
            body = parts2[1][1:] if len(parts2) > 1 else None
            # print("Parsime requesti: ",method," ",path,"\nHeader:",headers,"\n'",body,"'\n\n")
            reqs.append((method, path, headers, body))
    return reqs


def work_time():
    global start_time
    elapsed_time = time.monotonic() - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"


def do_request(session, user_id, url, method, path, headers, body, timeout):
    global total_requests, total_duration, min_duration, max_duration
    start = time.perf_counter()
    try:
        if method == "GET":
            r = session.get(url, headers=headers, timeout=timeout)
        else:
            r = session.post(url, headers=headers, data=body, timeout=timeout)
        duration = time.perf_counter() - start
        print(work_time(), user_id, method, path, r.status_code)

        with stats_lock:
            total_requests += 1
            total_duration += duration
            min_duration = min(min_duration, duration)
            max_duration = max(max_duration, duration)
            status_counts[r.status_code] = status_counts.get(r.status_code, 0) + 1

        if r.status_code != 200:
            print(f"VIGA!! Staatus: {r.status_code}")
            print("Request: ",method,    path,  "\nHeader:",  headers, "\n" + (body if body else "") + "\n" + r.text[:200] + "...\n" )
    except requests.exceptions.RequestException as e:
        duration = time.perf_counter() - start
        print(f"{work_time()} {user_id} {method} {path} ERROR: {e}")
        with stats_lock:
            total_requests += 1
            total_duration += duration
            status_counts["ERROR"] = status_counts.get("ERROR", 0) + 1


def user_worker(
    user_id,
    base_url,
    startup_requests_data,
    requests_data,
    rate_limiter,
    stop_time,
    verify_ssl,
    timeout,
):
    #print(work_time(), f"[User {user_id}] start")
    session = requests.Session()
    session.verify = verify_ssl

    if not session.verify:  # kui oleme kontrolli välja lülitanud, ei taha hoiatusi ka
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    try:
        # Startup päringud
        for method, path, headers, body in startup_requests_data:
            url = base_url + path
            try:
                do_request(session, user_id, url, method, path, headers, body, timeout)
            except Exception as e:
                print(f"[User {user_id}] startup request error: {e}")

        while time.monotonic() < stop_time:
            # print(work_time(), f"[User {user_id}] runtime left: stop_time-time=",(stop_time-time.time()))
            # print("runtime left: stop_time-time=",(stop_time-time.time()))
            # rate_limiter.wait(stop_time-time.time()) # rate limit peab olema alguses, muidu teeb iga kasutaja kohe esimese päringu ära
            # if time.time() > stop_time:
            #    print(work_time(), f"[User {user_id}] over time")
            #    return
            now = time.monotonic()
            if now >= stop_time:
                break
            if not rate_limiter.wait(stop_time, (work_time() + f" [User {user_id}]")):
                break

            method, path, headers, body = random.choice(requests_data)
            url = base_url + path
            try:
                do_request(session, user_id, url, method, path, headers, body, timeout)
            except Exception as e:
                print(f"[User {user_id}] request error: {e}")

    finally:
        session.close()


def stats_printer(stop_time):
    global start_time
    while time.monotonic() < stop_time and (stop_time - time.monotonic()) > 5:
        time.sleep(5)

        with stats_lock:
            if total_requests == 0:
                continue
            avg = total_duration / total_requests
            cur_min = min_duration if min_duration != float('inf') else 0
            cur_max = max_duration
            elapsed_time = time.monotonic() - start_time
            avg2 = total_requests / elapsed_time if elapsed_time > 0 else 0

            per_status = dict(status_counts)
        status_details = ", ".join( f"{status}={count}" for status, count in sorted(per_status.items(), key=lambda x: str(x[0]))   )
        print(
            f"[STATS] requests={total_requests}, "
            f"avg_duration_ms={avg * 1000:.2f} (min={cur_min*1000:.1f}, max={cur_max*1000:.1f}), total avg={avg2:.1f} req/s  "
            "runtime:", elapsed_time_tostr(elapsed_time)
        )
        print(f"         status breakdown: {status_details}")
        successful_requests = sum(
            count for status, count in per_status.items() if isinstance(status, int) and 200 <= status < 300
        )
        success_rate = successful_requests / elapsed_time if elapsed_time > 0 else 0
        print(f"         success (2xx) avg={success_rate:.1f} req/s")


def main():
    args = parse_args()

    startup_requests_data = []
    if args.s:
        try:
            startup_requests_data = load_requests(args.s)
        except FileNotFoundError:
            if args.s != "startup_requests.txt": # kui kasutaja ise määras ja ei leitud
                print(f"[WARNING] Startup faili '{args.s}' ei leitud.")
    
    requests_data = load_requests(args.f)
    if not requests_data:
        raise RuntimeError(f"{args.f} on tühi")

    rate_limiter = RateLimiter(args.n)
    stop_time = time.monotonic() + args.t

    threads = []

    print("[INFO] Start time: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

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
                args.timeout,
            ),
            daemon=True,
        )
        t.start()
        threads.append(t)

    stats_thread = threading.Thread(
        target=stats_printer,
        args=(stop_time,),
        daemon=True,
    )
    stats_thread.start()

    for t in threads:
        t.join()

    with stats_lock:
        avg = (total_duration / total_requests) if total_requests else 0
        cur_min = min_duration if min_duration != float('inf') else 0
        cur_max = max_duration
        elapsed_time = time.monotonic() - start_time  # kogu programmi tööaeg
        avg2 = total_requests / elapsed_time if elapsed_time > 0 else 0

        per_status = dict(status_counts)
    status_details = ", ".join( f"{status}={count}" for status, count in sorted(per_status.items(), key=lambda x: str(x[0]))    )
    print(f"\n[FINAL STATS] requests={total_requests}, avg_duration_ms={avg * 1000:.2f} (min={cur_min*1000:.1f}, max={cur_max*1000:.1f}), total avg={avg2:.1f} req/s   runtime:", elapsed_time_tostr(elapsed_time)    )
    print(f"              status breakdown: {status_details}")
    successful_requests = sum(
        count for status, count in per_status.items() if isinstance(status, int) and 200 <= status < 300
    )
    success_rate = successful_requests / elapsed_time if elapsed_time > 0 else 0
    print(f"              success (2xx) avg={success_rate:.1f} req/s")

    print("[INFO] End time: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))


def elapsed_time_tostr(elapsed_time):
    time_parts = []
    days = int(elapsed_time // 86400)
    hours = int((elapsed_time % 86400) // 3600)
    minutes = int((elapsed_time % 3600) // 60)
    seconds = int(elapsed_time % 60)

    if days > 0:
        time_parts.append(f"{days} päeva")
    if hours > 0:
        time_parts.append(f"{hours:02}h")
    if minutes > 0:
        time_parts.append(f"{minutes:02}min")
    if seconds > 0:
        time_parts.append(f"{seconds:02}s")
    if not time_parts:
        time_parts.append("0s")
    return(" ".join(time_parts))

if __name__ == "__main__":
    main()