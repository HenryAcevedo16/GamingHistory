import { Suspense } from "react";
import { ProjectEditor } from "@/components/projects/project-editor";

export default function ProjectPage({ params }: PageProps<"/projects/[id]">) {
  return <Suspense fallback={<p role="status" className="p-8">Cargando proyecto…</p>}><ProjectRoute params={params} /></Suspense>;
}

async function ProjectRoute({ params }: Pick<PageProps<"/projects/[id]">, "params">) {
  const { id } = await params;
  return <ProjectEditor key={id} id={id} />;
}
