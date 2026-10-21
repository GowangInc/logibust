#!/bin/sh
# Ubuntu/Mint amd64 packages, extracted only: no system package install or udev hooks.
set -eu
root="${HOME}/.cache/logibust"
mkdir -p "$root/packages" "$root/g810-led"
cd "$root/packages"
apt-get download g810-led libg810-led0 libhidapi-hidraw0
for package in g810-led_*.deb libg810-led0_*.deb libhidapi-hidraw0_*.deb; do
    dpkg-deb -x "$package" "$root/g810-led"
done
LD_LIBRARY_PATH="$root/g810-led/usr/lib/x86_64-linux-gnu" "$root/g810-led/usr/bin/g610-led" --help
