<?php


require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';

header('Content-Type: application/json; charset=utf-8');

try {
  $store = config_store();
  echo json_encode($store->listBasemaps(), JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['error' => $e->getMessage()]);
}
?>