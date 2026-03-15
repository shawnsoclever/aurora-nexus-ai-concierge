<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;

class ChatController extends Controller
{
    private function baseUrl(): string
    {
        return rtrim(env('FASTAPI_BASE_URL', 'http://127.0.0.1:8000'), '/');
    }

    public function index()
    {
        return view('chat');
    }

    public function support()
    {
        return view('support');
    }

    public function chat(Request $request)
    {
        $payload = [
            'session_id' => $request->input('session_id'),
            'user_id' => $request->input('user_id', 'web-user'),
            'message' => $request->input('message'),
        ];

        $response = Http::timeout(120)->post($this->baseUrl() . '/chat', $payload);

        return response()->json($response->json(), $response->status());
    }

    public function rooms(Request $request)
    {
        $query = [
            'session_id' => $request->query('session_id'),
            'user_id' => $request->query('user_id', 'web-user'),
            'checkin_date' => $request->query('checkin_date'),
            'checkout_date' => $request->query('checkout_date'),
            'guest_count' => $request->query('guest_count'),
            'room_type' => $request->query('room_type'),
        ];

        $response = Http::timeout(60)->get($this->baseUrl() . '/rooms', $query);

        return response()->json($response->json(), $response->status());
    }

    public function bookingPreview(Request $request)
    {
        $payload = [
            'session_id' => $request->input('session_id'),
            'guest_id' => $request->input('guest_id'),
            'guest_name' => $request->input('guest_name'),
            'stay_purpose' => $request->input('stay_purpose'),
            'checkin_date' => $request->input('checkin_date'),
            'checkout_date' => $request->input('checkout_date'),
            'room_type' => $request->input('room_type'),
            'room_id' => $request->input('room_id'),
            'guest_count' => $request->input('guest_count'),
        ];

        $response = Http::timeout(60)->post($this->baseUrl() . '/booking/preview', $payload);

        return response()->json($response->json(), $response->status());
    }

    public function booking(Request $request)
    {
        $payload = [
            'session_id' => $request->input('session_id'),
            'guest_id' => $request->input('guest_id'),
            'room_id' => $request->input('room_id'),
            'checkin_date' => $request->input('checkin_date'),
            'checkout_date' => $request->input('checkout_date'),
            'room_type' => $request->input('room_type'),
            'guest_count' => $request->input('guest_count'),
            'booking_source' => $request->input('booking_source', 'web-chat'),
        ];

        $response = Http::timeout(60)->post($this->baseUrl() . '/booking', $payload);

        return response()->json($response->json(), $response->status());
    }

    public function paymentPreview(Request $request)
    {
        $payload = [
            'session_id' => $request->input('session_id'),
            'booking_id' => $request->input('booking_id'),
        ];

        $response = Http::timeout(60)->post($this->baseUrl() . '/payment/preview', $payload);

        return response()->json($response->json(), $response->status());
    }

    public function payment(Request $request)
    {
        $payload = [
            'session_id' => $request->input('session_id'),
            'booking_id' => $request->input('booking_id'),
            'guest_id' => $request->input('guest_id'),
            'amount' => $request->input('amount'),
            'payment_status' => $request->input('payment_status', 'success'),
            'transaction_id' => $request->input('transaction_id'),
        ];

        $response = Http::timeout(60)->post($this->baseUrl() . '/payment', $payload);

        return response()->json($response->json(), $response->status());
    }

    public function complaint(Request $request)
    {
        $payload = [
            'session_id' => $request->input('session_id'),
            'user_id' => $request->input('user_id', 'support-web-user'),
            'booking_id' => $request->input('booking_id'),
            'guest_id' => $request->input('guest_id'),
            'issue' => $request->input('issue'),
            'resolution' => $request->input('resolution', ''),
        ];

        $response = Http::timeout(60)->post($this->baseUrl() . '/complaint', $payload);

        return response()->json($response->json(), $response->status());
    }
}
