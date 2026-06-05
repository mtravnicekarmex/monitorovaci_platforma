<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';
header('Content-Type: application/json; charset=utf-8');
echo json_encode(config_store()->listLayers(), JSON_UNESCAPED_UNICODE);
?>