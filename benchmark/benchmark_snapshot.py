import argparse
import math
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from timeit import default_timer

from PIL import Image
from psutil import cpu_percent, process_iter

from plate_recognition import recognition_api


def parse_arguments():
    parser = argparse.ArgumentParser(description="Benchmark SDK.")
    parser.add_argument(
        "--sdk-url",
        help="Url to self hosted sdk  For example, http://localhost:8080",
        default="http://localhost:8080",
    )
    parser.add_argument(
        "--threads", help="Use thread to parallelize API calls", default=4, type=int
    )
    parser.add_argument("--image", default="assets/car-4k.jpg")
    parser.add_argument("--mmc", action="store_true")
    parser.add_argument("--iterations", default=50, type=int)
    return parser.parse_args()


def print_table(results):
    if not results:
        return
    print("| Mode     | Resolution | Speed   | l_min  | l_max  |")
    print("| -------- | ---------- | ------- | ------ | ------ |")
    for result in results:
        print(
            "| {mode:8s} | {resolution:10s} | {avg:7.1f} | {min:6.1f} | {max:6.1f} |".format(
                **result
            )
        )


def call_duration(path, sdk_url, config, mmc):
    now = default_timer()
    with open(path, "rb") as fp:
        recognition_api(
            fp, sdk_url=sdk_url, config=config, mmc="true" if mmc else "false"
        )
    return (default_timer() - now) * 1000


def benchmark(args, executor):
    image = Image.open(args.image)
    for resolution in [(800, 600), (1280, 720), (1920, 1080), (2560, 1440)]:
        image.resize(resolution).save("/tmp/platerec-benchmark.jpg")
        for config in [{}, dict(mode="fast")]:
            now = default_timer()
            stats = list(
                executor.map(
                    partial(
                        call_duration, sdk_url=args.sdk_url, config=config, mmc=args.mmc
                    ),
                    ["/tmp/platerec-benchmark.jpg"] * args.iterations,
                )
            )
            duration = (default_timer() - now) * 1000
            yield dict(
                resolution="%sx%s" % resolution,
                mode=config.get("mode", "regular"),
                min=min(stats),
                max=max(stats),
                avg=duration / args.iterations,
            )


def mem_usage():
    usage = {}
    for process in process_iter():
        if "main.py" in process.cmdline() or "start.sh" in process.cmdline():
            usage[process.pid] = process.memory_info()
    return usage


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    sign = ""
    if size_bytes < 0:
        size_bytes *= -1
        sign = "-"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{sign}{s} {size_name[i]}"


def main():
    args = parse_arguments()
    initial_mem = mem_usage()
    cpu_percent()  # first time this is called it will return a meaningless 0.0
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        # Warmup
        list(
            executor.map(
                partial(call_duration, sdk_url=args.sdk_url, config={}, mmc=args.mmc),
                [args.image] * 2,
            )
        )
        # Benchmark
        results = list(benchmark(args, executor))

    # Memory Usage
    print(f"CPU: {cpu_percent()}%")
    for pid, mem in mem_usage().items():
        print(
            f"PID: {pid:5}, "
            f"RES {convert_size(mem.rss):10} ({convert_size(mem.rss - initial_mem[pid].rss):10}), "
            f"SHR {convert_size(mem.shared):10} ({convert_size(mem.shared - initial_mem[pid].shared):10})"
        )
    print_table(results)


if __name__ == "__main__":
    main()
