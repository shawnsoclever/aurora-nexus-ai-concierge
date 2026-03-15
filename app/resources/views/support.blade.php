<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aurora Nexus Hotel - Guest Support</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="/css/aurora-nexus.css" rel="stylesheet">
</head>
<body>
  <header class="site-header">
    <a href="/" class="brand-link" aria-label="Aurora Nexus Hotel Home">
      <span class="brand-mark" aria-hidden="true">✦</span>
      <span class="brand-name">Aurora Nexus Hotel</span>
    </a>
  </header>

  <main class="page-shell support-shell">
    <section class="card-glass support-card">
      <h1>Guest Support</h1>
      <p>Submit complaints or service requests. We will route your request to the hotel support agent.</p>

      <form id="supportForm" class="support-form">
        <label for="issueType">Issue Type</label>
        <select id="issueType" required>
          <option value="Complaint">Complaint</option>
          <option value="Service Request">Service Request</option>
        </select>

        <label for="bookingId">Booking ID (optional)</label>
        <input id="bookingId" type="text" placeholder="BKG-xxxxxxx">

        <label for="guestId">Guest ID</label>
        <input id="guestId" type="text" required>

        <label for="issueDescription">Description</label>
        <textarea id="issueDescription" rows="5" required placeholder="Example: Air conditioning not working, please change room"></textarea>

        <button id="submitSupportBtn" type="submit">Submit</button>
      </form>

      <div id="supportResult" class="support-result d-none" aria-live="polite"></div>
    </section>
  </main>

  <script>
    window.APP_CONFIG = {
      complaintEndpoint: '/complaint'
    };
  </script>
  <script src="/js/support.js"></script>
</body>
</html>
