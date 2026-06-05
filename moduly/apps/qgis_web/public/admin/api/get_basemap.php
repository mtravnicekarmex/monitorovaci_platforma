<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';

header('Content-Type: application/json; charset=utf-8');

try {
  $id = $_GET['id'] ?? null;
  if (!$id) throw new Exception("Chybí ID");

  $store = config_store();
  $rec = $store->getBasemap($id);
  if (!$rec) throw new Exception("Podklad nenalezen");

  echo json_encode($rec, JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
  http_response_code(404);
  echo json_encode(['error' => $e->getMessage()]);
}
?>