import AppFrame from '../../../../../components/AppFrame';
import ProjectSource from '../../../../../components/ProjectSource';
export default function SourcePage({params}:{params:{projectId:string;sourceId:string}}): JSX.Element { return <AppFrame><ProjectSource key={`${params.projectId}/${params.sourceId}`} scope={params}/></AppFrame>; }
