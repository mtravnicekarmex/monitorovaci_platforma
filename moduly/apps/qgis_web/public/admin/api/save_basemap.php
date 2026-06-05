<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';

header('Content-Type: application/json; charset=utf-8');

try {
  $data = json_decode(file_get_contents("php://input"), true);
  if (!$data) throw new Exception("Neplatná data");

  $store = config_store();
  $store->saveBasemap([
    'id' => $data['id'] ?? null,
    'title' => $data['title'] ?? '',
    'url' => $data['url'] ?? '',
    'attribution' => $data['attribution'] ?? '',
    'maxZoom' => $data['maxZoom'] ?? 22,
  ]);

  echo json_encode(['success' => true]);
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['success' => false, 'message' => $e->getMessage()]);
}
?>