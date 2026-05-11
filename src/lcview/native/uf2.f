      program prog
      implicit double precision (a-h,o-z)
      character *1 c
      character *16 c16
      dimension nt(300,300),freqb(300)

C  Czytamy starego freq-a

      open (1, file = 'freq')
      read (1,*) nb,nall
      do i = 1,nb
         read (1,*) freqb(i)
      end do
      do i = 1,nall
         read (1,*) (nt(i,j), j = 1,nb)
      end do
      close(1)

C  Czytamy ampl-a

      open (1, file = 'ampl')
      do i = 1,4
         read (1,'(a1)') c
      end do
      do i = 1,nb
         read (1,'(a16,f13.7)') c16,freqb(i)
      end do


C  Zapisujemy nowego

      open (1, file = 'freq')
      write (1,'(2i5)') nb,nall
      do i = 1,nb
         write (1,'(f12.6)') freqb(i)
      end do
      do i = 1,nall
         write (1,'(50i4)') (nt(i,j), j = 1,nb)
      end do
      stop
      end
