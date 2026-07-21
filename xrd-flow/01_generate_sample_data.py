"""
Generates a synthetic XRD-style scan (two_theta, intensity) with a few
realistic-looking peaks plus noise
"""
import csv
import math
import random

random.seed(42)


def gaussian(x, center, height, width):
    return height * math.exp(-((x - center) ** 2) / (2 * width**2))


# (peak center in 2-theta degrees, peak height, peak width)
PEAKS = [
    (28.4, 950, 0.15),
    (47.3, 620, 0.18),
    (56.1, 410, 0.12),
]


def main():
    rows = []
    x = 10.0
    while x <= 80.0:
        y = 20 + random.uniform(-5, 5)  # background + noise
        for center, height, width in PEAKS:
            y += gaussian(x, center, height, width)
        rows.append((round(x, 3), round(y, 2)))
        x += 0.05

    with open("xrd_scan_001.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["two_theta", "intensity"])
        writer.writerows(rows)

    print(f"Wrote xrd_scan_001.csv with {len(rows)} points and {len(PEAKS)} peaks")


if __name__ == "__main__":
    main()
