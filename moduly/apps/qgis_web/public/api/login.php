<?php
require_once __DIR__ . '/../../config.php';
require_once __DIR__ . '/../../includes/db.php';
if (session_status() !== PHP_SESSION_ACTIVE) session_start();

$email = trim($_POST['email'] ?? '');
$pass  = $_POST['password'] ?? '';

$ok = false;
$user = null;

if (!ALLOW_DEMO_LOGIN) {
  // --- Přihlášení z DB ---
  $stmt = db()->prepare('SELECT email, pass_hash, role FROM users WHERE email = :email LIMIT 1');
  $stmt->execute([':email' => $email]);
  $u = $stmt->fetch();
  if ($u && password_verify($pass, $u['pass_hash'])) {
    $ok   = true;
    $user = ['email' => $u['email'], 'role' => $u['role']];
  }
} else {
  // --- DEMO login ---
  // prostě plain kontrola, ať se to vždy chytí
  if (filter_var($email, FILTER_VALIDATE_EMAIL) && $pass === 'demo1234') {
    $ok   = true;
    $user = ['email' => $email, 'role' => 'admin']; // admin role pro demo
  }
}

if ($ok && $user) {
  session_regenerate_id(true);
  $_SESSION['user'] = $user;
  header('Location: /armex/public/dashboard.php');
  exit;
} else {
  header('Location: /armex/public/index.php?e=1');
  exit;
}
