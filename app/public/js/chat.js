const sessionKey = 'aurora_nexus_session_id';
const guestKey = 'aurora_nexus_guest_id';

let sessionId = localStorage.getItem(sessionKey);
if (!sessionId) {
  sessionId = crypto.randomUUID();
  localStorage.setItem(sessionKey, sessionId);
}

let guestId = localStorage.getItem(guestKey);
if (!guestId) {
  guestId = `GST-web-${crypto.randomUUID().slice(0, 8)}`;
  localStorage.setItem(guestKey, guestId);
}

const API = window.APP_CONFIG;

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const bookingLoaderEl = document.getElementById('bookingLoader');
const roomResultsEl = document.getElementById('roomResults');
const roomCardsEl = document.getElementById('roomCards');

const bookingState = {
  roomType: null,
  guestCount: null,
  checkinDate: null,
  checkoutDate: null,
  bookingSource: 'web-chat',
  roomsLoaded: false,
};

function escapeHtml(text) {
  return (text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function appendMessage(role, text) {
  const msg = document.createElement('article');
  msg.className = `chat-msg ${role === 'user' ? 'chat-user' : 'chat-ai'}`;
  msg.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setBusy(isBusy) {
  inputEl.disabled = isBusy;
  sendBtn.disabled = isBusy;
}

function showRoomLoader(show) {
  bookingLoaderEl.classList.toggle('d-none', !show);
}

function showRoomResults(show) {
  roomResultsEl.classList.toggle('d-none', !show);
}

function parseBookingData(message) {
  const text = message.toLowerCase();

  if (text.includes('deluxe')) bookingState.roomType = 'Deluxe';
  if (text.includes('standard')) bookingState.roomType = 'Standard';
  if (text.includes('suite')) bookingState.roomType = 'Suite';

  const countMatch = text.match(/(\d+)\s*(guest|guests|pax|people|person)/);
  if (countMatch) bookingState.guestCount = Number(countMatch[1]);

  const checkinMatch = text.match(/checkin\s*(\d{4}-\d{2}-\d{2})/);
  if (checkinMatch) bookingState.checkinDate = checkinMatch[1];

  const checkoutMatch = text.match(/checkout\s*(\d{4}-\d{2}-\d{2})/);
  if (checkoutMatch) bookingState.checkoutDate = checkoutMatch[1];

  if (text.includes('direct')) bookingState.bookingSource = 'direct';
}

function canSearchRooms() {
  return (
    !!bookingState.roomType
    && !!bookingState.guestCount
    && !!bookingState.checkinDate
    && !!bookingState.checkoutDate
  );
}

async function postChat(message) {
  const response = await fetch(API.chatEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      user_id: guestId,
      message,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail?.error?.message || data?.error?.message || 'Assistant temporarily unavailable.';
    throw new Error(detail);
  }
  return data;
}

function renderRooms(rooms) {
  roomCardsEl.innerHTML = '';
  if (!rooms || rooms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-rooms';
    empty.textContent = 'No available rooms found for your criteria.';
    roomCardsEl.appendChild(empty);
    showRoomResults(true);
    return;
  }

  rooms.forEach((room) => {
    const card = document.createElement('article');
    card.className = 'room-card';
    card.innerHTML = `
      <h3>Room ${escapeHtml(String(room.room_id || 'N/A'))}</h3>
      <p><strong>Type:</strong> ${escapeHtml(room.room_type || 'N/A')}</p>
      <p><strong>Floor:</strong> ${escapeHtml(String(room.floor || 'N/A'))}</p>
      <p><strong>Zone:</strong> ${escapeHtml(room.zone || 'N/A')}</p>
      <p><strong>Capacity:</strong> ${escapeHtml(String(room.capacity || 'N/A'))} Guests</p>
      <p><strong>Noise Level:</strong> ${escapeHtml(room.noise_level || 'N/A')}</p>
      <button type="button" data-room-id="${escapeHtml(String(room.room_id || ''))}" class="select-room-btn">Select Room</button>
    `;
    roomCardsEl.appendChild(card);
  });

  showRoomResults(true);
}

async function loadRoomsAndRender() {
  showRoomLoader(true);
  showRoomResults(false);
  roomCardsEl.innerHTML = '';

  try {
    const query = new URLSearchParams({
      session_id: sessionId,
      user_id: guestId,
      checkin_date: bookingState.checkinDate,
      checkout_date: bookingState.checkoutDate,
      guest_count: String(bookingState.guestCount),
      room_type: bookingState.roomType,
    });

    const response = await fetch(`${API.roomsEndpoint}?${query.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.detail?.error?.message || 'Unable to search rooms right now.');
    }

    bookingState.roomsLoaded = true;
    renderRooms(data.rooms || []);
  } catch (error) {
    appendMessage('assistant', `Room search failed: ${error.message}`);
  } finally {
    showRoomLoader(false);
  }
}

async function bookRoom(selectedRoomId) {
  try {
    setBusy(true);
    appendMessage('assistant', 'Processing your reservation, please wait...');

    // Step 1: Booking preview (recommendation → preview stage)
    const previewRes = await fetch(API.bookingPreviewEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        guest_id: guestId,
        room_id: selectedRoomId,
        checkin_date: bookingState.checkinDate,
        checkout_date: bookingState.checkoutDate,
        room_type: bookingState.roomType,
        guest_count: bookingState.guestCount,
      }),
    });
    const previewData = await previewRes.json();
    if (!previewRes.ok) {
      throw new Error(previewData?.detail?.error?.message || 'Booking preview failed.');
    }

    // Step 2: Create booking (preview → payment stage)
    const bookingRes = await fetch(API.bookingEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        guest_id: guestId,
        room_id: selectedRoomId,
        checkin_date: bookingState.checkinDate,
        checkout_date: bookingState.checkoutDate,
        room_type: bookingState.roomType,
        guest_count: bookingState.guestCount,
        booking_source: bookingState.bookingSource,
      }),
    });
    const bookingData = await bookingRes.json();
    if (!bookingRes.ok) {
      throw new Error(bookingData?.detail?.error?.message || 'Booking request failed.');
    }

    const bookingId = bookingData.booking_id;

    // Step 3: Payment preview (get total amount)
    const payPreviewRes = await fetch(API.paymentPreviewEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        booking_id: bookingId,
      }),
    });
    const payPreviewData = await payPreviewRes.json();
    if (!payPreviewRes.ok) {
      throw new Error(payPreviewData?.detail?.error?.message || 'Payment preview failed.');
    }

    // Step 4: Complete payment (payment → confirmation stage, sets payment_confirmed=true)
    const payRes = await fetch(API.paymentEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        booking_id: bookingId,
        guest_id: guestId,
        amount: payPreviewData.amount,
        payment_status: 'success',
        transaction_id: `TXN-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
      }),
    });
    const payData = await payRes.json();
    if (!payRes.ok) {
      throw new Error(payData?.detail?.error?.message || 'Payment failed.');
    }

    // Step 5: Build confirmation locally from the data we already have
    const nights = previewData.total_nights || 1;
    const totalPrice = typeof previewData.total_price === 'number' ? previewData.total_price.toFixed(2) : '—';
    const guestName = previewData.guest_name || guestId;
    const confirmMessage = [
      '─────────────────────────────────',
      'Booking Confirmed',
      '',
      `Booking ID:   ${bookingId}`,
      `Guest:        ${guestName}`,
      '',
      'Room Details',
      `Room ID:      ${previewData.room_id || bookingData.room_id}`,
      `Room Type:    ${previewData.room_type || bookingState.roomType}`,
      '',
      'Stay Details',
      `Check-in:     ${previewData.checkin_date || bookingState.checkinDate}`,
      `Check-out:    ${previewData.checkout_date || bookingState.checkoutDate}`,
      `Nights:       ${nights}`,
      `Guests:       ${bookingState.guestCount}`,
      '',
      `Total:        MYR ${totalPrice}`,
      `Payment:      Paid`,
      '',
      'Your reservation has been successfully confirmed.',
      'Please contact us if you require any additional services.',
      '─────────────────────────────────',
    ].join('\n');
    appendMessage('assistant', confirmMessage);
  } catch (error) {
    appendMessage('assistant', `Booking failed: ${error.message}`);
  } finally {
    setBusy(false);
  }
}

roomCardsEl.addEventListener('click', async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.classList.contains('select-room-btn')) return;

  const selectedRoomId = target.getAttribute('data-room-id');
  if (!selectedRoomId) return;

  showRoomResults(false);
  await bookRoom(selectedRoomId);
});

async function sendMessage() {
  const message = inputEl.value.trim();
  if (!message) return;

  appendMessage('user', message);
  inputEl.value = '';
  setBusy(true);

  try {
    parseBookingData(message);
    const data = await postChat(message);
    appendMessage('assistant', data.response || 'No response received.');

    if (!bookingState.roomsLoaded && canSearchRooms()) {
      await loadRoomsAndRender();
    }
  } catch (error) {
    appendMessage('assistant', error.message || 'Failed to reach backend service.');
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

appendMessage('assistant', 'Welcome to Aurora Nexus Hotel. I can help you book a room, answer questions, or route support requests.');

sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    sendMessage();
  }
});
