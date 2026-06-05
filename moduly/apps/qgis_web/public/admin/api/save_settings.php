<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';
header('Content-Type: application/json; charset=utf-8');

$payload = json_decode(file_get_contents('php://input'), true) ?: [];
$settings = [
  'app_base' => $payload['app_base'] ?? '',
  'db' => [
    'driver' => $payload['db']['driver'] ?? 'pgsql',
    'host'   => $payload['db']['host'] ?? '127.0.0.1',
    'port'   => (int)($payload['db']['port'] ?? 5432),
    'dbname' => $payload['db']['dbname'] ?? '',
    'user'   => $payload['db']['user'] ?? '',
    'pass'   => $payload['db']['pass'] ?? ''
  ]
];
config_store()->saveSettings($settings);
echo json_encode(['ok'=>true]);
?>