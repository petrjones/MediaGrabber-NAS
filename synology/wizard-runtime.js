// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted DSM integration patterns: see LICENSES/Synology-ExamplePackage-MIT.txt.
/* DSM 7.2.2+ Vue wizard. tools/build_spk.py replaces the two JSON literals. */
SYNO.SDS.PkgManApp.Custom.JsonpLoader.load((function () {
  'use strict';
  const kind = __KIND__;
  const cs = __CZECH__;
  const offline = __OFFLINE__;
  const hook = SYNO.SDS.PkgManApp.Custom.useHook;
  const headings = cs ? {install:'Nastavení MediaGrabber NAS',upgrade:'Aktualizace MediaGrabber NAS',uninstall:'Odinstalace MediaGrabber NAS'} : {install:'Set up MediaGrabber NAS',upgrade:'Update MediaGrabber NAS',uninstall:'Uninstall MediaGrabber NAS'};
  const Component = Vue.defineComponent({
    props: Object.assign({}, hook.props),
    setup: function (props) {
      const native = hook(props);
      const password = Vue.ref('');
      const confirmation = Vue.ref('');
      const removePrivate = Vue.ref(false);
      const headline = headings[kind];
      const valid = Vue.computed(function () {
        const n = Array.from(password.value).length;
        return kind !== 'install' || (n >= 14 && n <= 128 && password.value === confirmation.value && password.value.trim() === password.value && !/[\r\n]/.test(password.value));
      });
      const checkState = function (owner) {
        owner = owner || props.getOwner();
        if (!owner || !owner.getButton) return;
        native.checkState(owner);
        const next = owner.getButton('next');
        if (next) next.setDisabled(!valid.value);
      };
      Vue.watch([password, confirmation], function () { checkState(); });
      Vue.onMounted(function () { checkState(); });
      const getValues = function () {
        // Use Synology's executable ExamplePackage contract: one flat object.
        // The guide's Object[] example differs from that implementation; arrays
        // are not the flat name-to-string mapping required by that contract.
        return kind === 'install' ? {wizard_admin_password:password.value,wizard_admin_password_confirm:confirmation.value} : kind === 'uninstall' ? {wizard_remove_private_data:removePrivate.value?'yes':'no'} : {};
      };
      return {getNext:native.getNext,checkState:checkState,headline:headline,getValues:getValues,password:password,confirmation:confirmation,removePrivate:removePrivate};
    },
    render: function (h) {
      const nodes = [];
      if (kind === 'install') {
        nodes.push(h('p',cs ? 'Přihlašovací jméno aplikace bude admin. Zvol vlastní heslo o délce 14–128 znaků a zadej jej dvakrát. Heslo nesmí začínat ani končit mezerou.' : 'The application login name will be admin. Enter your own password of 14–128 characters twice, without leading or trailing whitespace.'));
        nodes.push(h('v-form',{attrs:{'syno-id':'mg-setup-form'}},[
          h('v-form-item',{props:{label:cs?'Heslo pro MediaGrabber':'MediaGrabber password'},attrs:{'syno-id':'mg-password-item'}},[
            h('v-input',{props:{type:'password',value:this.password},attrs:{'syno-id':'mg-password',autocomplete:'new-password'},on:{input:(value)=>{this.password=value;}}})
          ]),
          h('v-form-item',{props:{label:cs?'Zopakovat heslo':'Confirm password'},attrs:{'syno-id':'mg-confirmation-item'}},[
            h('v-input',{props:{type:'password',value:this.confirmation},attrs:{'syno-id':'mg-confirmation',autocomplete:'new-password'},on:{input:(value)=>{this.confirmation=value;}}})
          ])
        ]));
        nodes.push(h('p',cs ? 'Média budou ve sdílené složce MediaGrabber. Balíček připraví účet a oprávnění automaticky. Z nabídky DSM se administrátor přihlásí automaticky. Toto heslo slouží také pro přímý přístup na portu 8787 a jako záložní přihlášení.' : 'Media will be stored in the MediaGrabber shared folder. The package configures its account and permissions automatically. Opening from the DSM menu signs in a DSM administrator automatically. This password is also used for direct port 8787 access and as a fallback.'));
        nodes.push(h('p',offline ? (cs ? 'Obraz služby je součástí tohoto SPK. Instalace nepotřebuje stahovat jeho závislosti. Pro stahování médií a sledování zdrojů je internet nutný.' : 'The service image is included in this SPK; installation does not download its dependencies. Media downloads and source monitoring still require internet.') : (cs ? 'Tento vývojový SPK sestavuje službu při instalaci a potřebuje internet. Pro instalaci bez internetu použij vydání s přibaleným obrazem.' : 'This development SPK builds the service during installation and needs internet. For offline installation use a release with a bundled image.')));
        nodes.push(h('p',cs ? 'Při opětovné instalaci nad zachovanými daty se použije nově zadané heslo. Běžná aktualizace SPK původní heslo zachová.' : 'Reinstalling over retained data uses the newly entered password. A normal SPK upgrade keeps the existing password.'));
      } else if (kind === 'upgrade') {
        nodes.push(h('p',cs ? 'Fronta, historie, sledované zdroje, nastavení i heslo zůstanou zachované. Stažené soubory se nemění.' : 'Queue, history, watched sources, settings and password are retained. Downloaded media is unchanged.'));
        nodes.push(h('p',offline ? (cs ? 'Po zastavení se vytvoří soukromá záloha a načte se obraz přibalený v SPK. Aktualizace nepotřebuje stahovat závislosti.' : 'A private stopped-state backup is created and the image bundled with the SPK is loaded. Updating does not download dependencies.') : (cs ? 'Po zastavení služby se vytvoří soukromá záloha aplikačních dat. Tento vývojový SPK pak sestaví službu s připojením k internetu.' : 'After the service stops a private backup is created. This development SPK then builds the service using internet access.')));
      } else {
        nodes.push(h('p',cs ? 'Odstraní se služba a její projekt v Container Manageru. Stažená média ve sdílené složce MediaGrabber zůstanou na NASu.' : 'The service and its Container Manager project are removed. Downloaded media in the MediaGrabber shared folder stays on the NAS.'));
        nodes.push(h('label', {style:{display:'block',margin:'18px 0'}}, [
          h('input',{attrs:{type:'checkbox','syno-id':'mg-remove-private'},domProps:{checked:this.removePrivate},on:{change:(event)=>{this.removePrivate=event.target.checked;}}}),
          cs ? ' Odstranit také nastavení, historii, sledované zdroje, heslo a soukromé zálohy aplikace.' : ' Also remove application settings, history, watched sources, password and private backups.'
        ]));
        nodes.push(h('p',cs ? 'Tato volba je nevratná. Pokud ji nezaškrtneš, soukromá data se zachovají pro případnou opětovnou instalaci. Média se nemažou v žádné z těchto variant.' : 'This choice is irreversible. Leave it unchecked to retain private data for reinstallation. Neither choice deletes downloaded media.'));
      }
      return h('pkg-center-step-content',nodes);
    }
  });
  // Match the ES-module namespace emitted by the documented webpack JSONP build.
  const exports = {default:{name:'mediagrabber_'+kind,render:Component}};
  Object.defineProperty(exports,'__esModule',{value:true});
  if (typeof Symbol !== 'undefined' && Symbol.toStringTag) Object.defineProperty(exports,Symbol.toStringTag,{value:'Module'});
  return exports;
})());
