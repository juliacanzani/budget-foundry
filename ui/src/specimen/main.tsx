import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@tangible/ui/styles';
import '../theme.css';
import './specimen.css';
import { Specimen, type SpecimenData } from './Specimen';

// One self-contained file: the build inlines this bundle, the font and the data.
const data = JSON.parse(document.getElementById('specimen-data')!.textContent!) as SpecimenData;
createRoot(document.getElementById('root')!).render(<StrictMode><Specimen data={data} /></StrictMode>);
