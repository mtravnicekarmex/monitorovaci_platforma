<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';

header('Content-Type: application/json; charset=utf-8');

try {
  $data = json_decode(file_get_contents("php://input"), true);
  $id = $data['id'] ?? null;
  if (!$id) throw new Exception("Chybí ID");

  $store = config_store();
  $store->deleteBasemap($id);

  echo json_encode(['success' => true]);
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['success' => false, 'message' => $e->getMessage()]);
}
?>