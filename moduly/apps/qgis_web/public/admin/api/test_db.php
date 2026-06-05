<?php
require_once __DIR__ . "/../../../includes/db.php";

header('Content-Type: application/json; charset=utf-8');

try {
    $row = db()->query("SELECT NOW() AS t")->fetch();
    echo json_encode(['ok'=>true, 'server_time'=>$row['t']]);
} catch (Exception $e) {
    echo json_encode(['ok'=>false, 'msg'=>$e->getMessage()]);
}
?>