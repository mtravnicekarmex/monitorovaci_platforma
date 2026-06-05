<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';
header('Content-Type: application/json; charset=utf-8');
echo json_encode(['settings'=>config_store()->getSettings()], JSON_UNESCAPED_UNICODE);
?>