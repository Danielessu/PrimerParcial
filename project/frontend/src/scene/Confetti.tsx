import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

type ConfettiProps = {
  position: [number, number, number]
  active: boolean
}

export function Confetti({ position, active }: ConfettiProps) {
  const count = 100
  const groupRef = useRef<THREE.Group>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      position: new THREE.Vector3(),
      velocity: new THREE.Vector3(),
      rotation: new THREE.Euler(
        Math.random() * Math.PI,
        Math.random() * Math.PI,
        Math.random() * Math.PI,
      ),
      rotationSpeed: new THREE.Vector3(
        Math.random() * 5,
        Math.random() * 5,
        Math.random() * 5,
      ),
    }))
  }, [])

  const colors = [
    '#ef4444',
    '#facc15',
    '#22c55e',
    '#38bdf8',
    '#a855f7',
    '#f97316',
  ]

  useEffect(() => {
    if (!active) return

    particles.forEach((p) => {
      p.position.set(
        (Math.random() - 0.5) * 3,
        Math.random() * 1.5,
        (Math.random() - 0.5) * 3,
      )

      p.velocity.set(
        (Math.random() - 0.5) * 3,
        Math.random() * 4 + 2,
        (Math.random() - 0.5) * 3,
      )

      p.rotation.set(
        Math.random() * Math.PI,
        Math.random() * Math.PI,
        Math.random() * Math.PI,
      )
    })
  }, [active, particles])

  useFrame((_, delta) => {
    if (!active || !groupRef.current) return

    groupRef.current.children.forEach((child, i) => {
      const p = particles[i]

      p.velocity.y -= 6 * delta

      p.position.x += p.velocity.x * delta
      p.position.y += p.velocity.y * delta
      p.position.z += p.velocity.z * delta

      p.rotation.x += p.rotationSpeed.x * delta
      p.rotation.y += p.rotationSpeed.y * delta
      p.rotation.z += p.rotationSpeed.z * delta

      child.position.copy(p.position)
      child.rotation.copy(p.rotation)
    })
  })

  if (!active) return null

  return (
    <group ref={groupRef} position={position}>
      {particles.map((_, i) => (
        <mesh key={i}>
          <boxGeometry args={[0.12, 0.04, 0.06]} />
          <meshStandardMaterial color={colors[i % colors.length]} />
        </mesh>
      ))}
    </group>
  )
}
