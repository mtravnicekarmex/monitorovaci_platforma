<?php
require_once __DIR__ . '/auth_check.php';
if (($_SESSION['user']['role'] ?? '') !== 'admin') {
  http_response_code(403);
  echo 'Forbidden';
  exit;
}
?>