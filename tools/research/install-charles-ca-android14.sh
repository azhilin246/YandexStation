#!/system/bin/sh
set -eu

cert_hash="$1"
stage="/data/local/tmp/yandexstation-charles-ca"
apex_cacerts="/apex/com.android.conscrypt/cacerts"
system_cacerts="/system/etc/security/cacerts"

if ! grep -q " $apex_cacerts " /proc/mounts; then
    mkdir -p "$stage/apex-cacerts"
    cp -a "$apex_cacerts/." "$stage/apex-cacerts/"
    mount -t tmpfs tmpfs "$apex_cacerts"
    cp -a "$stage/apex-cacerts/." "$apex_cacerts/"
fi

install -m 0644 "$stage/$cert_hash.0" "$apex_cacerts/$cert_hash.0"
chown root:root "$apex_cacerts/$cert_hash.0"
chcon u:object_r:system_file:s0 "$apex_cacerts/$cert_hash.0" 2>/dev/null || true

if [ -d "$system_cacerts" ] && [ -w "$system_cacerts" ]; then
    install -m 0644 "$stage/$cert_hash.0" "$system_cacerts/$cert_hash.0"
    chown root:root "$system_cacerts/$cert_hash.0"
    chcon u:object_r:system_file:s0 "$system_cacerts/$cert_hash.0" 2>/dev/null || true
fi
