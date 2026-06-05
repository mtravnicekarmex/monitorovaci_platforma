<?php
require_once __DIR__ . "/../../../config.php";

header('Content-Type: application/json; charset=utf-8');

// Rozparsujeme DSN
$host = '';
$port = '';
$dbname = '';

if (preg_match('/host=([^;]+)/', DB_DSN, $m)) $host = $m[1];
if (preg_match('/port=([^;]+)/', DB_DSN, $m)) $port = $m[1];
if (preg_match('/dbname=([^;]+)/', DB_DSN, $m)) $dbname = $m[1];

echo json_encode([
    'settings' => [
        'app_base' => APP_NAME, // nebo jiné — UI to má ignorovat
        'db' => [
            'driver' => 'pgsql',
            'host'   => $host,
            'port'   => $port,
            'dbname' => $dbname,
            'user'   => DB_USER,
            'pass'   => '' // heslo nikdy nevracíme
        ]
    ]
]);
?>