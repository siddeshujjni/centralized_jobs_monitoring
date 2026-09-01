import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import JobDetail from './pages/JobDetail';
import Anomalies from './pages/Anomalies';
import MultiWorkspace from './pages/MultiWorkspace';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/multi" element={<MultiWorkspace />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/anomalies" element={<Anomalies />} />
      </Routes>
    </Layout>
  );
}
