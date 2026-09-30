import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage';
import IntelligentQAPage from './pages/IntelligentQAPage';
import StationsPage from './pages/StationsPage';
import StationDetailPage from './pages/StationDetailPage';
import RoutePlannerPage from './pages/RoutePlannerPage';

function App() {
  return (
    <Router>
      <div>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/stations" element={<StationsPage />} />
          <Route path="/stations/:id" element={<StationDetailPage />} />
          <Route path="/intelligent-qa" element={<IntelligentQAPage />} />
          <Route path="/route-planner" element={<RoutePlannerPage />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
