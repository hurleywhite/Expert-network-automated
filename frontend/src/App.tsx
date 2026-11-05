import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ProjectDetail from './pages/ProjectDetail';
import ExpertProfile from './pages/ExpertProfile';
import AuthGate from './components/AuthGate';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* The admin app sits behind the password gate. */}
        <Route path="/" element={<AuthGate><Dashboard /></AuthGate>} />
        <Route path="/projects/:projectId" element={<AuthGate><ProjectDetail /></AuthGate>} />
        <Route
          path="/projects/:projectId/experts/:expertId"
          element={<AuthGate><ExpertProfile /></AuthGate>}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
