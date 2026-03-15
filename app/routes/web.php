<?php

use App\Http\Controllers\ChatController;
use Illuminate\Support\Facades\Route;

Route::get('/', [ChatController::class, 'index']);
Route::get('/support', [ChatController::class, 'support']);
Route::post('/chat', [ChatController::class, 'chat']);
Route::get('/rooms', [ChatController::class, 'rooms']);
Route::post('/booking/preview', [ChatController::class, 'bookingPreview']);
Route::post('/booking', [ChatController::class, 'booking']);
Route::post('/payment/preview', [ChatController::class, 'paymentPreview']);
Route::post('/payment', [ChatController::class, 'payment']);
Route::post('/complaint', [ChatController::class, 'complaint']);
