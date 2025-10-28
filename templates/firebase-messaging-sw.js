// Import and initialize the Firebase SDK
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyA7mpyGe9VerX6ucQO14gTayWbjv91ZT3Y",
    authDomain: "developer-appoinment---n8n.firebaseapp.com",
    databaseURL: "https://developer-appoinment---n8n-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "developer-appoinment---n8n",
    storageBucket: "developer-appoinment---n8n.appspot.com",
    messagingSenderId: "714294036344",
    appId: "1:714294036344:web:c5ad6176758418ac2d6a8d",
    measurementId: "G-HPLX67C2EH"
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);

// Retrieve an instance of Firebase Messaging so that it can handle background messages.
const messaging = firebase.messaging();

// Optional: Handle background messages
messaging.onBackgroundMessage((payload) => {
  console.log('[firebase-messaging-sw.js] Received background message ', payload);
  // Customize notification here
  const notificationTitle = payload.notification.title || 'New Message';
  const notificationOptions = {
    body: payload.notification.body || '',
    icon: '/icon.png' // Make sure you have an icon.png file in your root
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

console.log('Firebase Messaging Service Worker initialized');