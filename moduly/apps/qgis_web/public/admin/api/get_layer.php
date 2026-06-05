<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';
header('Content-Type: application/json; charset=utf-8');
$id = $_GET['id'] ?? '';
$L = config_store()->getLayer($id);
if(!$L){ http_response_code(404); echo json_encode(['error'=>'not_found']); exit; }
echo json_encode($L, JSON_UNESCAPED_UNICODE);
?>