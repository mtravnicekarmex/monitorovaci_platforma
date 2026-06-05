<?php
require_once __DIR__ . '/../config.php';
if (session_status() !== PHP_SESSION_ACTIVE) session_start();
if (!empty($_SESSION['user'])) {
  header('Location: /armex/public/dashboard.php'); exit;
}
?>
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= APP_NAME ?> – Přihlášení</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="/armex/public/assets/css/styles.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container py-5">
    <div class="row justify-content-center">
      <div class="col-12 col-sm-10 col-md-6 col-lg-4">
        <div class="card shadow-sm">
          <div class="card-body p-4">
            <h1 class="h4 mb-3 text-center"><?= APP_NAME ?></h1>
            <p class="text-muted text-center mb-4">Přihlaste se do mapové prohlížečky[]</p>

            <?php if (!empty($_GET['e'])): ?>
              <div class="alert alert-danger py-2">Neplatné přihlašovací údaje.</div>
            <?php endif; ?>

            <form method="post" action="/armex/public/api/login.php">
              <div class="mb-3">
                <label class="form-label">E-mail</label>
                <input type="email" value="demo@armex.cz" class="form-control" name="email" required autofocus>
              </div>
              <div class="mb-3">
                <label class="form-label">Heslo</label>
                <input type="password" class="form-control" name="password" required>
              </div>
              <button class="btn btn-primary w-100">Přihlásit</button>
            </form>

          </div>
        </div>
        <p class="small text-center text-muted mt-3">© <?= date('Y') ?> ARMEX</p>
      </div>
    </div>
  </div>
</body>
</html>
