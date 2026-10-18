Dispatch now probes the actual run-record directories before native admission,
retry accounting or a background started message. A bounded exclusive no-follow
write/fsync/cleanup probe checks storage without a free-space threshold or
changing existing receipts or directory modes. Storage failures name the path
and advise checking disk space, mount health and permissions; native admission
I/O failures retain a distinct storage heading instead of advice to free a
budget group. Reports remain best-effort when storage itself cannot be written.
