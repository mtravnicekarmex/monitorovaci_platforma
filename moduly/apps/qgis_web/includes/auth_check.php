<?php
require_once __DIR__ . '/../config.php';
if (session_status() !== PHP_SESSION_ACTIVE) {
  session_start();
}

// ochrana chráněných stránek
if (empty($_SESSION['user'])) {
  header('Location: /armex/public/index.php');
  exit;
}
?>