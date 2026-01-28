import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Component that renders HTML from public folder
const HTMLPage = ({ htmlFile }) => {
  useEffect(() => {
    // Redirect to the HTML file in public folder
    window.location.href = `/${htmlFile}`;
  }, [htmlFile]);
  
  return <div>Loading...</div>;
};

// Home page redirect
const Home = () => <HTMLPage htmlFile="home.html" />;

// Auth page redirect
const Auth = () => <HTMLPage htmlFile="authorization.html" />;

// Dashboard redirect
const Dashboard = () => <HTMLPage htmlFile="client-dashboard.html" />;

// New Order redirect
const NewOrder = () => <HTMLPage htmlFile="client-order-configuration.html" />;

// Admin redirect
const Admin = () => <HTMLPage htmlFile="admin.html" />;

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/auth" element={<Auth />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/order/new" element={<NewOrder />} />
        <Route path="/staff/queue" element={<Admin />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
