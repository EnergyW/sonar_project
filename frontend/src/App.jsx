import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import ReviewsPage from "./pages/ReviewsPage";
import QuestionsPage from "./pages/QuestionsPage";
import StoreSettingsPage from "./pages/StoreSettingsPage";
import EmployeesPage from "./pages/EmployeesPage";
import AnalyticsPage from "./pages/AnalyticsPage";

function PrivateRoute({ children }) {
  const token = localStorage.getItem("token");
  return token ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="reviews" element={<ReviewsPage />} />
          <Route path="questions" element={<QuestionsPage />} />
          <Route path="settings" element={<StoreSettingsPage />} />
          <Route path="employees" element={<EmployeesPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
