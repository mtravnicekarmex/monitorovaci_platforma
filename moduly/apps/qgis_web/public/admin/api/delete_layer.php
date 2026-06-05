<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';
header('Content-Type: application/json; charset=utf-8');
$id = $_GET['id'] ?? '';
config_store()->deleteLayer($id);
echo json_encode(['ok'=>true]);
?>