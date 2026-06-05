<?php
// Základní konfigurace
define('APP_NAME', 'ARMEX Map');
define('SESSION_NAME', 'armexmap_sess');

// Bezpečné session cookies
session_name(SESSION_NAME);
session_set_cookie_params([
  'lifetime' => 0,
  'path' => '/',
  'domain' => '',
  'httponly' => true,
  'samesite' => 'Lax'
]);

// DB připojení (doplň podle sebe – stejné použije login i API)
define('DB_DSN', 'pgsql:host=SERVER2A;port=5432;dbname=ARMEX;');
define('DB_USER', 'qgis');
define('DB_PASS', 'Siga486.');

// Pro demo: povolit login i bez DB (FALSE = vyžaduje DB)
define('ALLOW_DEMO_LOGIN', true);

// Volitelné povolené originy pro CORS (interní použití)
define('ALLOWED_ORIGINS', ['*']);
?>