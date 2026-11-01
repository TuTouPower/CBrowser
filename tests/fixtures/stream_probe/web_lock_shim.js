(() => {
    if (window.__cbrowserIdentityGuard) return;
    window.__cbrowserIdentityGuard = true;
    window.__SELKIES_STREAMING_MODE__ = 'webrtc';
    const NativeWebSocket = window.WebSocket;
    let heldId = null;
    const acquisitions = new Map();

    function acquire(id) {
        if (heldId === id) return Promise.resolve(true);
        if (acquisitions.has(id)) return acquisitions.get(id);
        const pending = new Promise((resolve, reject) => {
            if (!navigator.locks) {
                reject(new Error('Web Locks required'));
                return;
            }
            navigator.locks.request('cbrowser_tab_lock_' + id,
                {ifAvailable: true}, lock => {
                    if (!lock) {
                        resolve(false);
                        return;
                    }
                    heldId = id;
                    resolve(true);
                    // The document owns the lock across signaling reconnects.
                    // Chrome releases it when the document is discarded.
                    return new Promise(() => {});
                }).catch(reject);
        });
        acquisitions.set(id, pending);
        pending.finally(() => acquisitions.delete(id)).catch(() => {});
        return pending;
    }

    window.WebSocket = new Proxy(NativeWebSocket, {
        construct(Target, args, NewTarget) {
            const socket = Reflect.construct(Target, args, NewTarget);
            const path = new URL(args[0], location.href).pathname;
            const signaling = path === '/api/webrtc/signaling'
                || /^\/stream\/[^/]+\/signal$/.test(path);
            if (!signaling) return socket;
            const nativeSend = socket.send.bind(socket);
            socket.send = data => {
                if (typeof data !== 'string' || !data.startsWith('HELLO client ')) {
                    return nativeSend(data);
                }
                const id = sessionStorage.getItem('selkies_tab_id');
                if (!id) {
                    socket.close(1008, 'tab_identity_required');
                    return;
                }
                acquire(id).then(acquired => {
                    if (socket.readyState !== NativeWebSocket.OPEN) return;
                    if (!acquired) {
                        sessionStorage.setItem('selkies_tab_id', crypto.randomUUID());
                        // Retry using the official client; never rewrite HELLO.
                        socket.close(1000, 'tab_collision_remap');
                        return;
                    }
                    nativeSend(data);
                }).catch(() => socket.close(1008, 'tab_identity_unavailable'));
            };
            return socket;
        }
    });
})();
