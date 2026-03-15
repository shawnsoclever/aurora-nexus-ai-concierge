<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aurora Nexus Hotel - AI Concierge</title>
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

  <main class="page-shell">
    <section class="hero-copy">
      <h1>AI Concierge Assistant</h1>
      <p>Book rooms, ask hotel questions, and get instant concierge support through natural conversation.</p>
    </section>

    <section class="chat-panel card-glass">
      <div id="messages" class="messages"></div>

      <div id="bookingLoader" class="booking-loader d-none" aria-live="polite">
        <div class="spinner-ring"></div>
        <p>Searching for available rooms...</p>
      </div>

      <div id="roomResults" class="room-results d-none">
        <h2>Available Rooms</h2>
        <div id="roomCards" class="room-cards"></div>
      </div>

      <div class="composer">
        <input id="messageInput" type="text" placeholder="Book a room, ask for services, or request support" autocomplete="off">
        <button id="sendBtn" type="button">Send</button>
      </div>
    </section>
  </main>

  <a class="support-fab" href="/support" aria-label="Guest Support">
    <span class="support-icon">🛟</span>
    <span>Guest Support</span>
  </a>

  <script>
    window.APP_CONFIG = {
      chatEndpoint: '/chat',
      roomsEndpoint: '/rooms',
      bookingPreviewEndpoint: '/booking/preview',
      bookingEndpoint: '/booking',
      paymentPreviewEndpoint: '/payment/preview',
      paymentEndpoint: '/payment',
    };
  </script>
  <script src="/js/chat.js"></script>
</body>
</html>
