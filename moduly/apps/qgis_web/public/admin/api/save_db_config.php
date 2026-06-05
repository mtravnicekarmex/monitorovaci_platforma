<?php
header('Content-Type: application/json; charset=utf-8');

$body = file_get_contents("php://input");
$data = json_decode($body, true);

if (!isset($data['db'])) {
    echo json_encode(['ok'=>false, 'msg'=>'Missing db config']);
    exit;
}

$db = $data['db'];

$dsn = "pgsql:host={$db['host']};port={$db['port']};dbname={$db['dbname']};";

$configPath = __DIR__ . "/../../../config.php";
$content = file_get_contents($configPath);

// bezpečná náhrada
$content = preg_replace("/define\('DB_DSN'.*?\);/",  "define('DB_DSN', '$dsn');", $content);
$content = preg_replace("/define\('DB_USER'.*?\);/", "define('DB_USER', '{$db['user']}');", $content);
$content = preg_replace("/define\('DB_PASS'.*?\);/", "define('DB_PASS', '{$db['pass']}');", $content);

file_put_contents($configPath, $content);

echo json_encode(['ok'=>true]);
?>