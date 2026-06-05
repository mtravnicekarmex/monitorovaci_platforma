<?php
declare(strict_types=1);
error_reporting(E_ALL);
ini_set('display_errors', '1');

// NEvyžaduje admin_check – jen ověření prostředí
echo "<h3>Admin health</h3>";
echo "<pre>";
echo "PHP: " . PHP_VERSION . "\n";
echo "SESSION active: " . (session_status() === PHP_SESSION_ACTIVE ? "yes" : "no") . "\n";

$cfg = __DIR__ . '/../../config/app_config.json';
echo "Config exists: " . (is_file($cfg) ? "yes" : "no") . " ($cfg)\n";
if (is_file($cfg)) {
  $j = json_decode(file_get_contents($cfg), true);
  echo "app_base: " . ($j['settings']['app_base'] ?? '(none)') . "\n";
}
echo "</pre>";
?>