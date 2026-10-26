
import * as THREE from "three";
import { TwinAvatar } from "/static/avatar.js";
import { attachOrientation } from "/static/pose-orientation.js";

const $ = id => document.getElementById(id);
let avatar, state, voice=false, lastSpeech=-1, renderedSummary;
let switching=false, orientationAttached=false;
let received=0;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache:"no-store"} : {
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
  return result;
}
function showError(error) {
  $("prompt").textContent = error.message || String(error);
  $("prompt").dataset.critical="true";
}
const deg = value => typeof value === "number" && Number.isFinite(value)
  ? `${value.toFixed(1)}?` : "Unavailable";

async function loadModel() {
  if (switching) return;
  switching=true;
  try {
    const result = avatar ? await avatar.setDesign($("design").value) : await createAvatar();
    $("model-status").textContent = result.ready
      ? "Demo model loaded." : result.reason || "Model unavailable.";
    if (result.ready && !orientationAttached) {
      attachOrientation(avatar);
      orientationAttached=true;
    }
    if (result.ready) avatar.recenter();
  } catch(error) { $("model-status").textContent=error.message; }
  finally {switching=false;}
}
async function createAvatar() {
  avatar=new TwinAvatar($("avatar"));
  const original=avatar.frameCamera.bind(avatar);
  const neutral=new THREE.Color(0x8a96a3), red=new THREE.Color(0xef4444);
  avatar.frameCamera=function(...args) {
    const result=original(...args);
    for (const side of ["left","right"]) for (const joint of ["hip","knee","ankle"]) {
      const marker=this.markers?.[side]?.[joint];
      if (!marker?.material?.color) continue;
      const active=state?.session && !state.session.paused && !state.camera_error
        && performance.now()-received<2000 && side===state.session.side;
      const reading=active ? state.feedback?.[joint] : null;
      const intensity=reading?.tracked && Number.isFinite(reading.intensity)
        ? Math.max(0,Math.min(1,reading.intensity)) : 0;
      marker.material.color.copy(neutral).lerp(red,intensity);
    }
    return result;
  };
  return avatar.load();
}
function paragraph(host,label,value) {
  const p=document.createElement("p");p.textContent=`${label}: ${value}`;host.append(p);
}
function chart(host,points,label) {
  const valid=points.filter(p=>Number.isFinite(p.average));
  if (valid.length<2) return;
  const canvas=document.createElement("canvas");
  canvas.width=620;canvas.height=200;canvas.className="trend";
  canvas.setAttribute("role","img");canvas.setAttribute("aria-label",label);
  host.append(canvas);
  const ctx=canvas.getContext("2d");if(!ctx)return;
  const low=Math.min(...valid.map(p=>p.average));
  const high=Math.max(...valid.map(p=>p.average));
  ctx.strokeStyle="#066e69";ctx.lineWidth=3;ctx.beginPath();
  valid.forEach((p,i)=>{
    const x=30+i*560/(valid.length-1),y=170-(p.average-low)*140/(high-low||1);
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);
  });ctx.stroke();
  valid.forEach(p=>paragraph(host,p.utc,deg(p.average)));
}
function summary(s) {
  if (!s || renderedSummary===s.id) return;
  renderedSummary=s.id;
  const host=$("summary");host.hidden=false;host.replaceChildren();
  const h=document.createElement("h2");h.textContent="Demo exercise summary";host.append(h);
  paragraph(host,"Exercise",s.exercise);
  paragraph(host,"Completed repetitions",s.reps_completed);
  paragraph(host,"Within demo form limits",s.valid_demo_reps);
  paragraph(host,"Layer B",`${s.target_reached} target reached; ${s.target_not_reached} target not reached`);
  paragraph(host,"Incomplete rep at stop",s.unfinished_rep?"Yes":"No");
  paragraph(host,"Reference note",s.reference_note);
  for(const [direction,d] of Object.entries(s.directions)) {
    const name=s.exercise==="ankle_pumps"
      ? direction==="positive"?"Dorsiflexion":"Plantarflexion" : "Moving joint";
    const title=document.createElement("h3");title.textContent=name;host.append(title);
    paragraph(host,"Peak AROM",deg(d.peak_arom));
    paragraph(host,"Reference",deg(d.reference));
    paragraph(host,"Layer A",d.assessment.label);
    paragraph(host,"Status",d.assessment.tag || "DEMO ? not approved");
    if(d.assessment.note)paragraph(host,"Note",d.assessment.note);
    paragraph(host,"Average per-rep peak",deg(d.average));
    paragraph(host,"Best completed rep",deg(d.best));
    paragraph(host,"Previous-session average",s.has_previous?deg(d.previous_average):"No previous session");
    paragraph(host,"Previous-session best",s.has_previous?deg(d.previous_best):"No previous session");
    paragraph(host,"Change",Number.isFinite(d.difference)
      ?`${d.difference>=0?"+":""}${d.difference.toFixed(1)}?`:"Unavailable");
    chart(host,[...d.trend,{utc:"Current",average:d.average}],`${name} demo trend`);
  }
  for(const [joint,d] of Object.entries(s.support)) {
    paragraph(host,`Layer C ? ${joint}`,
      Number.isFinite(d.within_percent)?`${d.within_percent.toFixed(1)}% within demo limits`:"Not assessed");
    paragraph(host,`${joint} evaluable interval coverage`,
      Number.isFinite(d.coverage_percent)?`${d.coverage_percent.toFixed(1)}%`:"Unavailable");
  }
  paragraph(host,"Approval","Synthetic demo only. No clinical approval.");
  paragraph(host,"Decision authority","Patient and physical therapist. This tool does not diagnose.");
}
function render(s) {
  state=s;received=performance.now();
  const session=s.session;
  const exercise=session?.exercise || $("exercise").value;
  const side=session?.side || $("side").value;
  const cfg=s.profile.exercises[exercise];
  const joints=s.angles?.[side]||{};
  $("start").disabled=Boolean(session);
  $("exercise").disabled=Boolean(session);
  $("side").disabled=Boolean(session);
  $("pause").disabled=!session;
  $("stop").disabled=!session;
  $("prompt").textContent=s.camera_error
    ||(session?.paused?"Demo paused.":s.prompt.text);
  $("prompt").dataset.critical=String(Boolean(s.camera_error)||s.prompt.priority>=80);
  $("reps").textContent=`${session?.reps.length ?? s.summary?.reps_completed ?? 0} completed`;
  $("timer").textContent=session
    ?`${Math.max(0,Math.ceil(s.profile.duration_seconds-s.elapsed))} seconds left`:"Demo idle";
  $("quality").textContent=s.camera_error?"Camera/tracking error":"Camera-inferred XYZ ? demo only";
  $("readings").replaceChildren();
  for(const joint of ["hip","knee","ankle"]) {
    const row=document.createElement("tr");
    for(const text of [
      joint, joints[joint]?.tracked?deg(joints[joint].angle):"Uncertain",
      s.feedback?.[joint]?.state || joints[joint]?.state || "Waiting"
    ]){const cell=document.createElement("td");cell.textContent=text;row.append(cell);}
    $("readings").append(row);
  }
  if(avatar?.root && !switching && !session?.paused) {
    avatar.update(
      Object.fromEntries(["hip","knee","ankle"].map(j=>[j,joints[j]?.tracked?joints[j].angle:null])),
      Object.fromEntries(["hip","knee","ankle"].map(j=>[j,joints[j]?.tracked?"ok":"lost"])),
      {posture:exercise==="prone_knee_flexion"?"prone":"supine",hip_motion:"flexion"},
      side
    );
    if(avatar.updateOrientation) avatar.updateOrientation(
      s.orientation3d,side,session?"exercising":"idle",cfg.moving
    );
  }
  if(voice && session && !session.paused && s.prompt.seq!==lastSpeech) {
    lastSpeech=s.prompt.seq;
    if("speechSynthesis" in window){
      speechSynthesis.cancel();
      speechSynthesis.speak(new SpeechSynthesisUtterance(s.prompt.text));
    }
  }
  summary(s.summary);
}
$("start").onclick=()=>api("/api/demo/start",{
  exercise:$("exercise").value,side:$("side").value,scope:$("design").value
}).then(()=>{$("summary").hidden=true;}).catch(showError);
$("stop").onclick=()=>{
  if("speechSynthesis" in window)speechSynthesis.cancel();
  api("/api/demo/stop",{}).catch(showError);
};
$("pause").onclick=()=>api("/api/demo/pause",{}).catch(showError);
$("neutral").onclick=()=>api("/api/demo/neutral",{}).catch(showError);
$("voice").onclick=()=>{
  voice=!voice;$("voice").textContent=voice?"Voice on":"Voice off";
  if(!voice&&"speechSynthesis" in window)speechSynthesis.cancel();
};
$("design").onchange=async()=>{
  try {await loadModel();await api("/api/demo/scope",{scope:$("design").value});}
  catch(error){showError(error);}
};
document.querySelectorAll("[data-joint]").forEach(button=>{
  button.onclick=()=>avatar?.setFocusJoint(button.dataset.joint);
});
$("recenter").onclick=()=>avatar?.recenter();
$("about").onclick=async()=>{
  $("dialog").showModal();
  try {
    const refs=await api("/api/demo/references");
    $("reference-text").textContent=JSON.stringify({
      notice:"Synthetic configurable demo presets; no clinical approval.",
      hip_method:"First tracked torso-relative thigh direction defined as zero.",
      profile:state?.profile,references:refs
    },null,2);
  }catch(error){$("reference-text").textContent=error.message;}
};
$("close").onclick=()=>$("dialog").close();
await loadModel();
async function poll(){
  try{render(await api("/api/demo/state"));}
  catch(error){showError(error);state=null;received=0;}
  setTimeout(poll,150);
}
poll();
