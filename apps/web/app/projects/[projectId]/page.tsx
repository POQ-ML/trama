import AppFrame from '../../../components/AppFrame';
import AcademicProject from '../../../components/AcademicProject';
export default function ProjectPage({params}:{params:{projectId:string}}): JSX.Element { return <AppFrame><AcademicProject key={params.projectId} projectId={params.projectId}/></AppFrame>; }
