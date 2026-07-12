import Image from "next/image";

const capabilities = [
  "Engineering organizations that ship",
  "Regulated medical-device software",
  "AI adoption with disciplined governance",
  "Cybersecurity & DevSecOps modernization",
  "Architecture, product, and delivery alignment",
  "Technical strategy across global teams",
];

const milestones = [
  {
    date: "2024 — now",
    company: "Karl Storz North America",
    role: "Associate Director, Software Engineering",
    note: "Leading a 60+ person global engineering organization across embedded imaging, cybersecurity, DevSecOps, and AI-enabled delivery.",
  },
  {
    date: "Jul 2025 — now",
    company: "KINEXUS US LLC",
    role: "Founder & Software Engineer",
    note: "Creating practical connected-technology solutions for homes and businesses, with an emphasis on thoughtful design, reliable automation, and hands-on partnership.",
  },
  {
    date: "2018 — 2024",
    company: "1012 Consulting",
    role: "Co-owner & Software Engineer",
    note: "Built tailored technology solutions spanning smart-home systems, connected products, cloud infrastructure, and custom digital experiences.",
  },
  {
    date: "2012 — 2024",
    company: "From founder to technical leader",
    role: "Kinexus · VTG · Quantum Integration · Karl Storz",
    note: "A cross-disciplinary path through IoT, telematics, cloud platforms, embedded systems, and enterprise-scale product delivery.",
  },
];

const writing = [
  ["01", "Building AI-first engineering teams", "On turning enthusiasm into durable operating models."],
  ["02", "The leadership work behind reliable software", "How clear systems make room for better decisions."],
  ["03", "Regulated doesn’t mean slow", "Notes on shipping responsibly in high-stakes environments."],
];

function Arrow() {
  return <span aria-hidden="true" className="text-xl leading-none">↗</span>;
}

export default function Home() {
  return (
    <main className="overflow-hidden bg-[#f4f3ef] text-[#11110f]">
      <section className="min-h-screen border-b border-black/15 px-5 pb-10 pt-5 sm:px-8 lg:px-12">
        <nav className="mx-auto flex max-w-7xl items-center justify-between text-xs font-bold uppercase tracking-[0.17em]">
          <a href="#top" className="tracking-[0.24em]">J10L</a>
          <div className="hidden gap-7 md:flex">
            <a className="link-underline" href="#work">Work</a>
            <a className="link-underline" href="#consulting">Consulting</a>
            <a className="link-underline" href="#writing">Writing</a>
          </div>
          <a className="link-underline" href="#contact">Let&apos;s talk</a>
        </nav>

        <div id="top" className="mx-auto grid max-w-7xl gap-10 pb-10 pt-20 sm:pt-28 lg:grid-cols-[1.28fr_.72fr] lg:items-end lg:pt-36">
          <div>
            <p className="mb-6 text-sm font-bold uppercase tracking-[0.17em] text-black/55">Software engineering director · consultant</p>
            <h1 className="display-text max-w-4xl text-[clamp(4.2rem,10.4vw,9.8rem)] leading-[0.82] tracking-[-0.085em]">
              Make the
              <br />
              difficult <em className="font-normal">deliver.</em>
            </h1>
            <div className="mt-11 max-w-xl border-l-2 border-black pl-5 text-lg leading-relaxed text-black/72 sm:text-xl">
              I lead global teams through the messy, consequential work of building software people can trust—where product ambition, technical depth, and responsibility must move together.
            </div>
            <div className="mt-10 flex flex-wrap gap-3">
              <a className="button-primary" href="#contact">Start a conversation <Arrow /></a>
              <a className="button-secondary" href="#work">Explore the work <span aria-hidden="true">↓</span></a>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-md lg:max-w-none">
            <div className="absolute -left-4 -top-4 z-10 grid h-14 w-14 place-items-center rounded-full bg-[#d7ff3f] text-2xl shadow-sm">👋</div>
            <div className="relative aspect-[4/5] overflow-hidden rounded-[1.8rem] bg-black">
              <Image
                src="/images/profile-joeran-bw.png"
                alt="Joeran Kinzel"
                fill
                priority
                sizes="(max-width: 1024px) 90vw, 34vw"
                className="object-cover grayscale contrast-110"
              />
            </div>
            <p className="mt-3 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.16em] text-black/55"><span>Santa Barbara, California</span><span>English · Deutsch</span></p>
          </div>
        </div>
      </section>

      <section id="consulting" className="border-b border-black/15 bg-[#11110f] px-5 py-20 text-[#f4f3ef] sm:px-8 sm:py-28 lg:px-12">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[.72fr_1.28fr]">
          <p className="eyebrow text-[#d7ff3f]">What I help make possible</p>
          <div>
            <h2 className="display-text max-w-4xl text-5xl leading-[0.9] tracking-[-0.065em] sm:text-7xl">Better systems. <em className="font-normal">Braver</em> decisions.</h2>
            <p className="mt-9 max-w-2xl text-lg leading-relaxed text-white/67 sm:text-xl">I partner with leaders and teams navigating moments that demand more than a roadmap: scaling an organization, untangling legacy systems, modernizing a delivery model, or making AI useful without making risk someone else&apos;s problem.</p>
            <ul className="mt-12 grid gap-x-10 border-t border-white/20 pt-6 sm:grid-cols-2">
              {capabilities.map((capability, index) => (
                <li key={capability} className="flex gap-4 border-b border-white/15 py-4 text-base sm:text-lg"><span className="font-mono text-xs text-[#d7ff3f]">0{index + 1}</span>{capability}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section id="work" className="border-b border-black/15 px-5 py-20 sm:px-8 sm:py-28 lg:px-12">
        <div className="mx-auto max-w-7xl">
          <div className="mb-12 flex flex-wrap items-end justify-between gap-6"><div><p className="eyebrow">Selected path</p><h2 className="display-text mt-5 text-5xl tracking-[-0.06em] sm:text-7xl">Work with weight.</h2></div><span className="grid h-14 w-14 place-items-center rounded-full border border-black/25 text-2xl">⚙️</span></div>
          <div className="grid gap-0 border-t border-black/20">
            {milestones.map((milestone) => (
              <article key={milestone.company} className="grid gap-5 border-b border-black/20 py-8 md:grid-cols-[.55fr_1.25fr_1.2fr] md:py-10">
                <p className="font-mono text-xs uppercase tracking-[0.14em] text-black/50">{milestone.date}</p>
                <div><h3 className="text-2xl font-bold tracking-[-0.045em] sm:text-3xl">{milestone.company}</h3><p className="mt-1 text-sm font-bold uppercase tracking-[0.12em] text-black/52">{milestone.role}</p></div>
                <p className="max-w-xl leading-relaxed text-black/67">{milestone.note}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="grid border-b border-black/15 lg:grid-cols-2">
        <div className="relative min-h-[27rem] bg-[#11110f] lg:min-h-[39rem]"><Image src="/images/leadership-still-life.png" alt="Abstract monochrome composition of technology and architectural forms" fill sizes="(max-width: 1024px) 100vw, 50vw" className="object-cover grayscale contrast-125" /></div>
        <div className="flex flex-col justify-center px-5 py-20 sm:px-12 lg:px-16"><p className="eyebrow">The through-line</p><blockquote className="display-text mt-7 max-w-xl text-4xl leading-[0.96] tracking-[-0.055em] sm:text-6xl">“The job is not to make technology more complicated. It&apos;s to make meaningful progress possible.”</blockquote><p className="mt-8 max-w-lg leading-relaxed text-black/63">From embedded medical systems to distributed teams and connected products, my work centers on a simple standard: leave the people, product, and system stronger than you found them.</p></div>
      </section>

      <section id="writing" className="border-b border-black/15 bg-white px-5 py-20 sm:px-8 sm:py-28 lg:px-12">
        <div className="mx-auto max-w-7xl"><div className="flex flex-wrap items-end justify-between gap-6"><div><p className="eyebrow">Coming soon</p><h2 className="display-text mt-5 text-5xl tracking-[-0.06em] sm:text-7xl">Notes from the field.</h2></div><p className="max-w-xs text-sm leading-relaxed text-black/60">A future home for essays on engineering leadership, AI, systems thinking, and the work behind the work.</p></div>
          <div className="mt-12 grid border-t border-black/20 md:grid-cols-3">{writing.map(([number, title, description]) => <article key={number} className="group border-b border-black/20 py-7 md:border-b-0 md:px-8 md:py-9 md:not-last:border-r md:first:pl-0 md:last:pr-0"><span className="font-mono text-xs text-black/45">{number}</span><h3 className="mt-10 text-2xl font-bold tracking-[-0.04em] group-hover:underline">{title}</h3><p className="mt-4 max-w-xs leading-relaxed text-black/60">{description}</p><span className="mt-8 inline-block text-sm font-bold uppercase tracking-[0.13em] text-black/45">In progress</span></article>)}</div>
        </div>
      </section>

      <footer id="contact" className="bg-[#d7ff3f] px-5 py-20 sm:px-8 sm:py-28 lg:px-12"><div className="mx-auto max-w-7xl"><p className="eyebrow">Let&apos;s make something work</p><h2 className="display-text mt-6 max-w-5xl text-[clamp(3.7rem,8vw,7.8rem)] leading-[0.83] tracking-[-0.078em]">Have a difficult problem?<br /><em className="font-normal">Say hello.</em></h2><div className="mt-14 grid gap-8 border-t border-black/25 pt-7 sm:grid-cols-3"><a className="contact-link" href="mailto:joeran@kinexus.us">Email <Arrow /></a><a className="contact-link" href="https://www.linkedin.com/in/joeran-kinzel/" target="_blank" rel="noreferrer">LinkedIn <Arrow /></a><a className="contact-link" href="https://github.com/j10l" target="_blank" rel="noreferrer">GitHub <Arrow /></a></div><div className="mt-20 flex flex-wrap justify-between gap-4 border-t border-black/25 pt-5 text-xs font-bold uppercase tracking-[0.14em]"><span>© {new Date().getFullYear()} Joeran Kinzel</span><a className="link-underline" href="#top">Back to top ↑</a></div></div></footer>
    </main>
  );
}
