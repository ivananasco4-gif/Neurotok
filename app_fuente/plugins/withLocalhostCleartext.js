// Plugin de configuración de Expo: permite HTTP SOLO a 127.0.0.1 y localhost.
// La app habla con el backend que corre en el propio teléfono (http://127.0.0.1:8000) y Android
// release bloquea HTTP por defecto. Cualquier otro dominio sigue exigiendo HTTPS.
const fs = require('fs');
const path = require('path');
const { withAndroidManifest, withDangerousMod } = require('expo/config-plugins');

const XML = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false" />
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="false">127.0.0.1</domain>
    <domain includeSubdomains="false">localhost</domain>
  </domain-config>
</network-security-config>
`;

module.exports = function withLocalhostCleartext(config) {
  // 1) el archivo res/xml/network_security_config.xml (se escribe tras copiar la plantilla nativa)
  config = withDangerousMod(config, [
    'android',
    async (cfg) => {
      const dir = path.join(cfg.modRequest.platformProjectRoot, 'app', 'src', 'main', 'res', 'xml');
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, 'network_security_config.xml'), XML);
      return cfg;
    },
  ]);
  // 2) referenciarlo desde el AndroidManifest; el tráfico en claro global queda explícitamente apagado
  return withAndroidManifest(config, (cfg) => {
    const app = cfg.modResults.manifest.application[0];
    app.$['android:networkSecurityConfig'] = '@xml/network_security_config';
    app.$['android:usesCleartextTraffic'] = 'false';
    return cfg;
  });
};
