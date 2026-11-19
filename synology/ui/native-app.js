// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted DSM integration patterns: see LICENSES/Synology-ExamplePackage-MIT.txt.
// MediaGrabber.cgi completes this closure with a validated DSM loader token.
(function (loaderToken) {
    'use strict';
    SYNO.namespace('SYNO.SDS.App.MediaGrabberNAS');
    function validToken(value) { return typeof value === 'string' && /^[a-zA-Z0-9_.-]{1,256}$/.test(value); }
    function currentToken() {
        var session = SYNO.SDS.Session;
        return session && validToken(session.SynoToken) ? session.SynoToken : (validToken(loaderToken) ? loaderToken : '');
    }
    SYNO.SDS.App.MediaGrabberNAS.Instance = Vue.extend({
        data: function () { return { iframeUrl: '', launchError: '' }; },
        mounted: function () {
            var self = this, token = currentToken();
            if (!token) {
                self.launchError = 'DSM-TOKEN-MISSING: Obnov DSM a otevři aplikaci jeho ikonou. / Refresh DSM and open the app from its menu.';
                return;
            }
            fetch('/webman/3rdparty/MediaGrabberNAS/dsm-login.cgi', {
                method: 'GET', credentials: 'same-origin', cache: 'no-store',
                headers: { 'Accept': 'application/json', 'X-Syno-Token': token }
            }).then(function (response) {
                return response.json().then(function (value) {
                    if (!response.ok) throw new Error(value.error || 'DSM authentication failed.');
                    if (!value || !/^[a-f0-9]{64}$/.test(value.ticket)) throw new Error('Invalid DSM launch response.');
                    self.iframeUrl = '/mediagrabber/#dsm-ticket=' + value.ticket;
                });
            }).catch(function (error) { self.launchError = error.message || 'DSM authentication failed.'; });
        },
        render: function (h) {
            var content;
            if (this.iframeUrl) {
                content = h('iframe', { attrs: { src: this.iframeUrl, title: 'MediaGrabber NAS', referrerpolicy: 'no-referrer' },
                    style: { width: '100%', height: '100%', border: '0', display: 'block' } });
            } else {
                content = h('div', { style: { padding: '24px' } }, [h('h2', 'MediaGrabber NAS'),
                    h('p', this.launchError || 'Ověřuji přihlášení DSM… / Verifying DSM sign-in…'),
                    this.launchError ? h('a', { attrs: { href: '/mediagrabber/', target: '_blank', rel: 'noopener noreferrer' } },
                        'Přihlásit heslem aplikace / Use application password') : null]);
            }
            return h('v-app-instance', { attrs: { 'class-name': 'SYNO.SDS.App.MediaGrabberNAS.Instance' } }, [
                h('v-app-window', { ref: 'appWindow', attrs: { 'syno-id': 'SYNO.SDS.App.MediaGrabberNAS.Window' },
                    props: { width: 1200, height: 800, resizable: true, maximizable: true, minimizable: true } },
                    [h('div', { style: { width: '100%', height: '100%' } }, [content])])
            ]);
        }
    });
